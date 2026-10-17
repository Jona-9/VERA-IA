"""
Capa de servicios de la interfaz: arma el contexto de la demo (repositorio, modelo, política,
orquestador, simulación y servidor SMTP local) y expone consultas listas para las vistas.

Las vistas no conocen SQLite ni los módulos de otros integrantes; solo llaman a funciones de aquí.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st
import yaml

from src.agent.orchestrator import DailyCycleOrchestrator, NoticeDispatcher, SmtpNoticeDispatcher
from src.analytics.model import RiskModel
from src.analytics.signals import compute_signals_for_account
from src.data.generator import PortfolioGenerator
from src.data.sqlite_repo import SQLitePortfolioRepository
from src.domain.entities import Account, NoticeStatus, PeriodRecord
from src.mail.server import SQLiteCaptureStore, start_embedded_server
from src.policy.bandit import BanditSendDaySelector
from src.policy.config import PolicyConfig, load_policy_config
from src.simulation.engine import CustomerBehavior, SimulationEngine
from src.tools.reevaluate_tool import ReevaluateClientTool

ROOT = Path(__file__).resolve().parents[2]
SEED = 42
START_DATE = date(2026, 10, 15)
SIM_CUSTOMERS = 60
BENCHMARK_PATH = ROOT / "reports" / "benchmark_results.json"


@dataclass
class AppContext:
    repo: SQLitePortfolioRepository
    policy: PolicyConfig
    model: RiskModel
    orchestrator: DailyCycleOrchestrator
    engine: SimulationEngine
    reevaluate: ReevaluateClientTool
    selector: BanditSendDaySelector
    smtp_ok: bool


def _db_path() -> Path:
    configured = os.environ.get("VERAIA_DB")
    if configured:
        return Path(configured)
    config = yaml.safe_load((ROOT / "config" / "config.yaml").read_text(encoding="utf-8")) or {}
    return ROOT / config.get("database", {}).get("path", "data/portfolio_demo.db")


def _ensure_database(path: Path) -> None:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        PortfolioGenerator(seed=SEED, cutoff_date=START_DATE).populate_database(str(path), SIM_CUSTOMERS)


def _ensure_model(db_path: Path) -> RiskModel:
    model_path = ROOT / "reports" / "risk_model.joblib"
    if model_path.exists():
        return RiskModel.load(str(model_path))
    from src.cli.train_model import load_from_sqlite

    features, target = load_from_sqlite(str(db_path), START_DATE)
    model = RiskModel(random_state=SEED, cv=3).fit(features, target)
    model.save(str(model_path))
    return model


@st.cache_resource(show_spinner="Preparando la demo…")
def get_context() -> AppContext:
    db_path = _db_path()
    _ensure_database(db_path)
    repo = SQLitePortfolioRepository(str(db_path))
    policy = load_policy_config(ROOT / "config" / "politica.yaml")
    model = _ensure_model(db_path)

    smtp_ok = True
    try:
        start_embedded_server(store=SQLiteCaptureStore(db_path))
    except OSError:
        smtp_ok = False  # puerto ocupado: la demo sigue, sin captura SMTP real

    selector = BanditSendDaySelector(policy, seed=SEED)
    orchestrator = DailyCycleOrchestrator(repo, model, policy, selector=selector)
    dispatcher: NoticeDispatcher = SmtpNoticeDispatcher(repo)
    engine = SimulationEngine(
        repo, orchestrator, CustomerBehavior(seed=SEED), dispatcher, start_date=START_DATE,
        on_payment=lambda e: selector.record_outcome(e.account_id, e.pay_date <= e.due_date),
    )
    engine.ensure_started()
    return AppContext(repo, policy, model, orchestrator, engine, ReevaluateClientTool(orchestrator), selector, smtp_ok)


def reset_demo() -> None:
    """Regenera la cartera con la semilla y reinicia la simulación al día inicial."""
    db_path = _db_path()
    get_context.clear()
    db_path.unlink(missing_ok=True)
    BENCHMARK_PATH.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Consultas para las vistas
# ---------------------------------------------------------------------------


def review_cases(ctx: AppContext) -> List[Dict[str, Any]]:
    """Cola pendiente con días al vencimiento recalculados a la fecha simulada."""
    today = ctx.engine.current_date
    cases = []
    for case in ctx.repo.get_review_queue():
        account = ctx.repo.get_account(case["account_id"])
        customer = ctx.repo.get_customer(account.customer_id) if account else None
        case["days_to_due"] = (account.due_date - today).days if account else case["days_to_due"]
        case["customer_name"] = customer.full_name if customer else case["account_id"]
        cases.append(case)
    cases.sort(key=lambda c: (abs(c["days_to_due"]) if c["days_to_due"] < 0 else c["days_to_due"], c["case_id"]))
    return cases


def is_early_signal(signals, days_to_due: int, paid: bool) -> bool:
    """Buen pagador con deterioro incipiente: uso alto, pagos mínimos sostenidos y sin atrasos."""
    return (
        not paid
        and days_to_due >= 0
        and signals.credit_utilization_ratio >= 0.90
        and signals.consecutive_min_payments >= 3
        and signals.historical_delinquency_rate <= 0.2
    )


def portfolio_frame(ctx: AppContext) -> pd.DataFrame:
    """Una fila por cliente con la última evaluación a la fecha simulada."""
    day = ctx.engine.current_date
    evaluations = {}
    for evaluation in ctx.repo.get_evaluations():  # más recientes primero
        if evaluation["evaluation_date"][:10] <= day.isoformat():
            evaluations.setdefault(evaluation["account_id"], evaluation)
    pending_cases = {c["account_id"] for c in ctx.repo.get_review_queue()}

    rows = []
    for account in ctx.repo.get_portfolio_accounts(day):
        customer = ctx.repo.get_customer(account.customer_id)
        history = [PeriodRecord(**h.model_dump()) for h in ctx.repo.get_period_history(account.account_id, day)]
        signals = compute_signals_for_account(Account(**account.model_dump()), history, day)
        evaluation = evaluations.get(account.account_id, {})
        days_to_due = (account.due_date - day).days
        paid = account.status == "PAID" or account.current_balance <= 0
        rows.append({
            "account_id": account.account_id,
            "Cliente": customer.full_name if customer else account.customer_id,
            "Correo": customer.email if customer else "",
            "Vence": account.due_date,
            "days_to_due": days_to_due,
            "Saldo": account.current_balance,
            "Límite": account.credit_limit,
            "Uso": account.current_balance / account.credit_limit if account.credit_limit else 0.0,
            "Estado": account.status,
            "Pagó": paid,
            "Riesgo": evaluation.get("risk_band", "—"),
            "Probabilidad": evaluation.get("calibrated_probability"),
            "Evidencia": evaluation.get("evidence_quality", "—"),
            "Acción": evaluation.get("action_type", "—"),
            "Regla": evaluation.get("rule_applied", "—"),
            "Explicación": evaluation.get("explanation", ""),
            "En revisión": account.account_id in pending_cases,
            "Señal temprana": is_early_signal(signals, days_to_due, paid),
            "signals": signals,
        })
    return pd.DataFrame(rows)


def notices_frame(ctx: AppContext) -> pd.DataFrame:
    names = {}
    for account in ctx.repo.get_portfolio_accounts(ctx.engine.current_date):
        customer = ctx.repo.get_customer(account.customer_id)
        names[account.account_id] = customer.full_name if customer else account.customer_id
    rows = [
        {
            "notice_id": n["notice_id"],
            "account_id": n["account_id"],
            "Cliente": names.get(n["account_id"], n["account_id"]),
            "Fecha": n["scheduled_date"][:10],
            "Tono": n["tone"],
            "Estado": n["status"],
            "Asunto": n["subject"],
            "Texto": n["body_text"],
            "Validación": n["validation_status"],
            "Motivo": n.get("rejection_reason"),
        }
        for n in ctx.repo.get_notices()
    ]
    return pd.DataFrame(rows, columns=[
        "notice_id", "account_id", "Cliente", "Fecha", "Tono", "Estado", "Asunto", "Texto", "Validación", "Motivo",
    ])


def todays_notice_counts(ctx: AppContext) -> Dict[str, int]:
    today = ctx.engine.current_date.isoformat()
    counts = {"programados": 0, "enviados": 0, "retenidos": 0}
    for notice in ctx.repo.get_notices():
        if notice["scheduled_date"][:10] != today:
            continue
        if notice["status"] == NoticeStatus.APPROVED.value:
            counts["programados"] += 1
        elif notice["status"] in (NoticeStatus.DISPATCHED.value, NoticeStatus.CAPTURED.value):
            counts["enviados"] += 1
        elif notice["status"] == NoticeStatus.REJECTED.value:
            counts["retenidos"] += 1
    return counts
