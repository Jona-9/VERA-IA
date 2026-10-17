"""
Motor de reproducción histórica día por día (RF-19, T026).

Reproduce la operación diaria sobre la cartera sintética: a primera hora aplica los pagos que
los clientes simulados hacen ese día, a las 09:00 cierra la revisión (el orquestador evalúa y
deriva casos) y a las 10:00 despacha los avisos aprobados. Nada mira al futuro: cada día solo
usa datos hasta su fecha de corte (Principio IV).

Los clientes se simulan con `CustomerBehavior`, un modelo declarado y semillado (no es evidencia
real): cada cliente tiene una fecha natural de pago y los recordatorios pueden adelantarla.
La respuesta de los clientes y la revisión humana son simuladas (ver README, supuestos).
"""

from __future__ import annotations

import random
import sqlite3
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Callable, Dict, List, Optional

from src.agent.orchestrator import (
    CycleReport,
    DailyCycleOrchestrator,
    DispatchReport,
    NoticeDispatcher,
)
from src.data.repository import AccountDTO, PeriodRecordDTO
from src.data.sqlite_repo import SQLitePortfolioRepository
from src.domain.entities import NoticeStatus
from src.tools.reevaluate_tool import ReevaluateClientTool

SENT_STATUSES = (NoticeStatus.DISPATCHED.value, NoticeStatus.CAPTURED.value)

# Probabilidad base de que un recordatorio preventivo adelante el pago según los días de
# antelación con que llega (supuesto del simulador; más cerca del vencimiento ayuda más).
REMINDER_LIFT = {1: 0.12, 2: 0.22, 3: 0.16, 4: 0.12, 5: 0.10, 6: 0.08, 7: 0.06}
POST_DUE_RESPONSE = 0.45


@dataclass
class CustomerProfile:
    account_id: str
    due_date: date
    natural_pay_date: Optional[date]  # None: no paga dentro del horizonte simulado
    responsiveness: float
    in_clearing: bool = False


class CustomerBehavior:
    """Modelo semillado de pago de clientes; mismo comportamiento para cualquier estrategia."""

    def __init__(self, seed: int = 42, clearing_delay_days: int = 2):
        self.seed = seed
        self.clearing_delay_days = clearing_delay_days

    def build_profile(
        self,
        account: AccountDTO,
        history: List[PeriodRecordDTO],
        pending_dates: List[date],
        start_date: date,
    ) -> CustomerProfile:
        rng = random.Random(f"{self.seed}:{account.account_id}")
        delinquency = (sum(1 for r in history if r.days_past_due > 0) / len(history)) if history else 0.25
        utilization = account.current_balance / account.credit_limit if account.credit_limit else 0.0
        p_on_time = min(0.92, max(0.08, 0.88 - 0.9 * delinquency - 0.3 * max(0.0, utilization - 0.85)))
        responsiveness = rng.uniform(0.5, 1.0)

        if pending_dates:
            pay = max(max(pending_dates) + timedelta(days=self.clearing_delay_days + 1), start_date)
            return CustomerProfile(account.account_id, account.due_date, pay, responsiveness, in_clearing=True)

        if rng.random() < p_on_time:
            pay: Optional[date] = account.due_date - timedelta(days=rng.choice([0, 0, 0, 1, 1, 2]))
        else:
            pay = account.due_date + timedelta(days=rng.randint(2, 14)) if rng.random() > 0.25 * delinquency + 0.1 else None
        if pay is not None and pay < start_date:
            # Ya vencido a la fecha de corte y sin pago registrado: se comporta como pagador tardío.
            pay = start_date + timedelta(days=rng.randint(1, 6)) if rng.random() < 0.8 else None
        return CustomerProfile(account.account_id, account.due_date, pay, responsiveness)

    def apply_notice(self, profile: CustomerProfile, pay_date: Optional[date], notice_date: date) -> Optional[date]:
        """Nueva fecha de pago tras recibir un aviso el `notice_date` (solo si aún no pagó)."""
        if pay_date is not None and pay_date <= notice_date:
            return pay_date
        rng = random.Random(f"{self.seed}:{profile.account_id}:{notice_date.isoformat()}")
        offset = (notice_date - profile.due_date).days
        if offset < 0:
            chance = min(0.95, REMINDER_LIFT.get(-offset, 0.05) * 2 * profile.responsiveness)
            reacts = rng.random() < chance
            new_pay = min(notice_date + timedelta(days=rng.randint(1, 2)), profile.due_date)
        else:
            chance = POST_DUE_RESPONSE * profile.responsiveness
            reacts = rng.random() < chance
            new_pay = notice_date + timedelta(days=rng.randint(1, 2))
        if not reacts:
            return pay_date
        return new_pay if pay_date is None else min(pay_date, new_pay)

    def pay_date(self, profile: CustomerProfile, notice_dates: List[date]) -> Optional[date]:
        pay = profile.natural_pay_date
        for notice_date in sorted(notice_dates):
            pay = self.apply_notice(profile, pay, notice_date)
        return pay


@dataclass
class PaymentEvent:
    account_id: str
    pay_date: date
    due_date: date


@dataclass
class DayResult:
    cycle_date: date
    payments: List[PaymentEvent] = field(default_factory=list)
    cycle: Optional[CycleReport] = None
    dispatch: Optional[DispatchReport] = None


PHASE_REVIEW = "REVIEW"  # evaluado, esperando cierre de 09:00 / despacho de 10:00
PHASE_DISPATCHED = "DISPATCHED"  # despachado; listo para avanzar


class SimulationEngine:
    def __init__(
        self,
        repo: SQLitePortfolioRepository,
        orchestrator: DailyCycleOrchestrator,
        behavior: CustomerBehavior,
        dispatcher: NoticeDispatcher,
        start_date: date,
        auto_review: bool = False,
        on_payment: Optional[Callable[[PaymentEvent], None]] = None,
    ):
        self.repo = repo
        self.orchestrator = orchestrator
        self.behavior = behavior
        self.dispatcher = dispatcher
        self.start_date = start_date
        self.auto_review = auto_review
        self.on_payment = on_payment
        self.payments: List[PaymentEvent] = []
        self._profiles: Dict[str, CustomerProfile] = {}
        self._reevaluate = ReevaluateClientTool(orchestrator)
        self._init_state_table()

    # -- estado persistente (tabla propia en la misma base SQLite) ------------------------

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.repo.db_path)

    def _init_state_table(self) -> None:
        with self._connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS simulation_state (key TEXT PRIMARY KEY, value TEXT NOT NULL)")

    def _get(self, key: str) -> Optional[str]:
        with self._connect() as conn:
            row = conn.execute("SELECT value FROM simulation_state WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def _set(self, key: str, value: str) -> None:
        with self._connect() as conn:
            conn.execute("INSERT OR REPLACE INTO simulation_state (key, value) VALUES (?, ?)", (key, value))

    @property
    def current_date(self) -> date:
        value = self._get("current_date")
        return date.fromisoformat(value) if value else self.start_date

    @property
    def phase(self) -> Optional[str]:
        return self._get("phase")

    @property
    def day_number(self) -> int:
        return (self.current_date - self.start_date).days + 1

    # -- ciclo diario ------------------------------------------------------------------

    def ensure_started(self) -> None:
        """Primer arranque: evalúa el día inicial para que la interfaz tenga qué mostrar."""
        if self.phase is None:
            self.begin_day(self.start_date)

    def begin_day(self, day: date) -> DayResult:
        """Pagos de la mañana y corte de revisión: deja avisos aprobados y casos pendientes."""
        result = DayResult(cycle_date=day)
        result.payments = self._apply_customer_payments(day)
        result.cycle = self.orchestrator.run_evaluation(day)
        self._set("current_date", day.isoformat())
        self._set("phase", PHASE_REVIEW)
        return result

    def close_day(self) -> DispatchReport:
        """Cierre de revisión (09:00) y despacho (10:00) del día actual."""
        day = self.current_date
        if self.auto_review:
            self._auto_review(day)
        report = self.orchestrator.close_review_and_dispatch(day, self.dispatcher)
        self._set("phase", PHASE_DISPATCHED)
        return report

    def advance_day(self) -> DayResult:
        return self.begin_day(self.current_date + timedelta(days=1))

    def run_days(self, days: int) -> List[DayResult]:
        """Avanza `days` días completos (despacho incluido) desde el estado actual."""
        results: List[DayResult] = []
        self.ensure_started()
        for _ in range(days):
            if self.phase == PHASE_REVIEW:
                self.close_day()
            results.append(self.advance_day())
        return results

    # -- clientes simulados ---------------------------------------------------------------

    def _profile(self, account: AccountDTO) -> CustomerProfile:
        profile = self._profiles.get(account.account_id)
        if profile is None:
            history = self.repo.get_period_history(account.account_id, self.start_date)
            pending = [p.payment_date for p in self.repo.get_pending_payments(account.account_id, self.start_date)
                       if p.status == "IN_PROCESS"]
            profile = self.behavior.build_profile(account, history, pending, self.start_date)
            self._profiles[account.account_id] = profile
        return profile

    def _apply_customer_payments(self, day: date) -> List[PaymentEvent]:
        events: List[PaymentEvent] = []
        for account in self.repo.get_portfolio_accounts(day):
            if account.status == "PAID" or account.current_balance <= 0:
                continue
            sent = [date.fromisoformat(n["scheduled_date"][:10]) for n in self.repo.get_notices(account.account_id)
                    if n["status"] in SENT_STATUSES]
            pay = self.behavior.pay_date(self._profile(account), sent)
            if pay is None or pay > day:
                continue
            self.repo.update_payment_record(account.account_id, day, account.current_balance, "CLIENTE_SIM")
            event = PaymentEvent(account.account_id, day, account.due_date)
            events.append(event)
            self.payments.append(event)
            if self.on_payment:
                self.on_payment(event)
        return events

    def _auto_review(self, day: date) -> None:
        """Revisión humana simulada: confirma pagos en trámite y libera el resto."""
        for case in self.repo.get_review_queue():
            pending = [p for p in self.repo.get_pending_payments(case["account_id"], day) if p.status == "IN_PROCESS"]
            self._reevaluate.correct_payment_and_reevaluate(
                case_id=case["case_id"],
                account_id=case["account_id"],
                cutoff_date=day,
                actor="ANALISTA_SIM",
                notes="Revisión simulada",
                payment_date=pending[0].payment_date if pending else None,
                amount=pending[0].amount if pending else None,
            )
