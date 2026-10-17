"""
Benchmark: agente adaptativo vs. campaña fija tradicional por segmento (RF-17, T024/T025).

Ambas estrategias se ejecutan sobre la misma cartera sintética (regenerada con la semilla, no la
base de la demo en curso) y con el mismo `CustomerBehavior`, de modo que la única diferencia es
a quién y cuándo se avisa. La respuesta de los clientes es un supuesto del simulador, no
evidencia real.

Campaña fija: el segmento se define por uso de línea y cada segmento recibe un calendario fijo de
avisos, sin consultar riesgo ni pagos en trámite; solo deja de avisar a quien ya pagó.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from src.agent.orchestrator import DailyCycleOrchestrator, NullDispatcher
from src.analytics.model import RiskModel
from src.data.generator import PortfolioGenerator
from src.data.sqlite_repo import SQLitePortfolioRepository
from src.policy.bandit import BanditSendDaySelector
from src.policy.config import PolicyConfig
from src.simulation.engine import SENT_STATUSES, CustomerBehavior, CustomerProfile, SimulationEngine

# Calendario fijo (días respecto al vencimiento; negativo = antes) por segmento de uso de línea.
FIXED_SEGMENTS = {
    "Uso bajo (< 50 %)": [-3, 2],
    "Uso medio (50–80 %)": [-3, -1, 2],
    "Uso alto (> 80 %)": [-5, -3, -1, 1, 3],
}
LOW_RISK_BANDS = ("BAJA", "MODERADA")
CLEARING_DELAY_DAYS = 2


@dataclass
class StrategyMetrics:
    name: str
    total_notices: int = 0
    notices_low_moderate: int = 0
    notices_while_payment_in_process: int = 0
    paid_before_due: int = 0
    paid_on_time: int = 0
    paid_total: int = 0
    avg_anticipation_days: float = 0.0
    accounts: int = 0
    notices_by_band: Dict[str, int] = field(default_factory=dict)

    @property
    def on_time_rate(self) -> float:
        return self.paid_on_time / self.accounts if self.accounts else 0.0


@dataclass
class BenchmarkResult:
    seed: int
    cutoff_date: date
    horizon_days: int
    agent: StrategyMetrics
    fixed: StrategyMetrics

    @property
    def low_moderate_reduction(self) -> float:
        base = self.fixed.notices_low_moderate
        return 1 - self.agent.notices_low_moderate / base if base else 0.0

    def to_dict(self) -> dict:
        data = asdict(self)
        data["cutoff_date"] = self.cutoff_date.isoformat()
        data["low_moderate_reduction"] = self.low_moderate_reduction
        data["agent"]["on_time_rate"] = self.agent.on_time_rate
        data["fixed"]["on_time_rate"] = self.fixed.on_time_rate
        return data


def _finish(metrics: StrategyMetrics, pay_dates: Dict[str, Optional[date]], due: Dict[str, date]) -> None:
    anticipations = []
    for account_id, pay in pay_dates.items():
        if pay is None:
            continue
        metrics.paid_total += 1
        if pay <= due[account_id]:
            metrics.paid_on_time += 1
            anticipations.append((due[account_id] - pay).days)
        if pay < due[account_id]:
            metrics.paid_before_due += 1
    metrics.avg_anticipation_days = sum(anticipations) / len(anticipations) if anticipations else 0.0


def _segment(utilization: float) -> str:
    if utilization < 0.5:
        return "Uso bajo (< 50 %)"
    if utilization <= 0.8:
        return "Uso medio (50–80 %)"
    return "Uso alto (> 80 %)"


def run_benchmark(
    model: RiskModel,
    policy: PolicyConfig,
    seed: int = 42,
    cutoff_date: date = date(2026, 10, 15),
    customers: int = 60,
    horizon_days: int = 21,
    output_path: Optional[Path] = None,
) -> BenchmarkResult:
    behavior = CustomerBehavior(seed=seed, clearing_delay_days=CLEARING_DELAY_DAYS)
    with tempfile.TemporaryDirectory() as tmp:
        repo = PortfolioGenerator(seed=seed, cutoff_date=cutoff_date).populate_database(
            db_path=str(Path(tmp) / "benchmark.db"), num_customers=customers
        )
        agent, band_at_start = _run_agent(repo, model, policy, behavior, seed, cutoff_date, horizon_days)
        fixed = _run_fixed(repo_path=Path(tmp) / "fixed.db", seed=seed, cutoff_date=cutoff_date, customers=customers,
                           behavior=behavior, horizon_days=horizon_days, band_at_start=band_at_start)
    result = BenchmarkResult(seed, cutoff_date, horizon_days, agent, fixed)
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def _run_agent(repo, model, policy, behavior, seed, cutoff_date, horizon_days):
    selector = BanditSendDaySelector(policy, seed=seed)
    orchestrator = DailyCycleOrchestrator(repo, model, policy, selector=selector)
    engine = SimulationEngine(
        repo, orchestrator, behavior, NullDispatcher(), start_date=cutoff_date, auto_review=True,
        on_payment=lambda e: selector.record_outcome(e.account_id, e.pay_date <= e.due_date),
    )
    engine.run_days(horizon_days)

    accounts = {a.account_id: a for a in repo.get_portfolio_accounts(cutoff_date)}
    band_at_start = {
        e["account_id"]: e["risk_band"]
        for e in repo.get_evaluations() if e["evaluation_date"][:10] == cutoff_date.isoformat()
    }
    metrics = StrategyMetrics(name="Agente adaptativo", accounts=len(accounts))
    pay_dates: Dict[str, Optional[date]] = {a: None for a in accounts}
    for event in engine.payments:
        pay_dates[event.account_id] = event.pay_date
    pending = _pending_by_account(repo, cutoff_date)
    for notice in repo.get_notices():
        if notice["status"] not in SENT_STATUSES:
            continue
        sent_on = date.fromisoformat(notice["scheduled_date"][:10])
        _count_notice(metrics, band_at_start.get(notice["account_id"], "BAJA"),
                      _in_clearing(pending.get(notice["account_id"], []), sent_on))
    _finish(metrics, pay_dates, {a: acc.due_date for a, acc in accounts.items()})
    return metrics, band_at_start


def _pending_by_account(repo, cutoff_date) -> Dict[str, List[date]]:
    result: Dict[str, List[date]] = {}
    for account in repo.get_portfolio_accounts(cutoff_date):
        dates = [p.payment_date for p in repo.get_pending_payments(account.account_id, cutoff_date)
                 if p.status == "IN_PROCESS"]
        if dates:
            result[account.account_id] = dates
    return result


def _in_clearing(pending_dates: List[date], day: date) -> bool:
    return any(d <= day < d + timedelta(days=CLEARING_DELAY_DAYS) for d in pending_dates)


def _count_notice(metrics: StrategyMetrics, band: str, in_clearing: bool) -> None:
    metrics.total_notices += 1
    metrics.notices_by_band[band] = metrics.notices_by_band.get(band, 0) + 1
    if band in LOW_RISK_BANDS:
        metrics.notices_low_moderate += 1
    if in_clearing:
        metrics.notices_while_payment_in_process += 1


def _run_fixed(repo_path, seed, cutoff_date, customers, behavior, horizon_days, band_at_start) -> StrategyMetrics:
    repo = PortfolioGenerator(seed=seed, cutoff_date=cutoff_date).populate_database(
        db_path=str(repo_path), num_customers=customers
    )
    accounts = repo.get_portfolio_accounts(cutoff_date)
    pending = _pending_by_account(repo, cutoff_date)
    profiles: Dict[str, CustomerProfile] = {}
    schedules: Dict[str, List[date]] = {}
    for account in accounts:
        profiles[account.account_id] = behavior.build_profile(
            account, repo.get_period_history(account.account_id, cutoff_date),
            pending.get(account.account_id, []), cutoff_date,
        )
        utilization = account.current_balance / account.credit_limit if account.credit_limit else 0.0
        schedules[account.account_id] = [account.due_date + timedelta(days=o) for o in FIXED_SEGMENTS[_segment(utilization)]]

    metrics = StrategyMetrics(name="Campaña fija", accounts=len(accounts))
    sent: Dict[str, List[date]] = {a.account_id: [] for a in accounts}
    for offset in range(horizon_days):
        day = cutoff_date + timedelta(days=offset)
        for account in accounts:
            aid = account.account_id
            pay = behavior.pay_date(profiles[aid], sent[aid])
            already_paid = pay is not None and pay <= day
            if already_paid or day not in schedules[aid]:
                continue
            sent[aid].append(day)
            _count_notice(metrics, band_at_start.get(aid, "BAJA"), _in_clearing(pending.get(aid, []), day))

    horizon_end = cutoff_date + timedelta(days=horizon_days)
    pay_dates: Dict[str, Optional[date]] = {}
    for account in accounts:
        pay = behavior.pay_date(profiles[account.account_id], sent[account.account_id])
        pay_dates[account.account_id] = pay if pay is not None and pay <= horizon_end else None
    _finish(metrics, pay_dates, {a.account_id: a.due_date for a in accounts})
    return metrics
