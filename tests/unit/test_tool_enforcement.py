"""
Pruebas exhaustivas de límites deterministas de `ScheduleNoticeTool` (T011, T014):
fuera de ventana, exceso de avisos, separación mínima, tono inválido, pago
registrado y pago en proceso.

Usa un repositorio mock en memoria (diccionarios y dataclasses) que
implementa exactamente la firma de `PolicyRepositoryPort`
(subconjunto de `PortfolioRepository`), sin depender de SQLite.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Optional

import pytest

from src.domain.entities import RiskBand, Tone
from src.policy.config import PolicyConfig
from src.tools.schedule_tool import (
    ERR_ALREADY_PAID,
    ERR_INVALID_TONE_FOR_BAND,
    ERR_MAX_NOTICES_EXCEEDED,
    ERR_MIN_SEPARATION_VIOLATED,
    ERR_OUTSIDE_WINDOW,
    ERR_PAYMENT_IN_PROGRESS,
    ERR_UNKNOWN_ACCOUNT,
    ScheduleNoticeInput,
    ScheduleNoticeTool,
)


@dataclass
class _Account:
    account_id: str
    current_balance: float
    status: str
    due_date: date


@dataclass
class _PendingPayment:
    payment_id: str
    amount: float
    payment_date: date
    status: str


@dataclass
class _MockRepository:
    """Repositorio en memoria que implementa el subconjunto requerido por `PolicyRepositoryPort`."""

    accounts: List[_Account] = field(default_factory=list)
    pending_payments: Dict[str, List[_PendingPayment]] = field(default_factory=dict)
    notices_count: int = 0
    last_notice_date: Optional[date] = None
    saved_notices: List[dict] = field(default_factory=list)

    def get_portfolio_accounts(self, cutoff_date: date) -> List[_Account]:
        return self.accounts

    def get_pending_payments(self, account_id: str, cutoff_date: date) -> List[_PendingPayment]:
        return self.pending_payments.get(account_id, [])

    def get_account_notices_count(self, account_id: str, cycle_start_date: date, cutoff_date: date) -> int:
        return self.notices_count

    def get_last_notice_date(self, account_id: str) -> Optional[date]:
        return self.last_notice_date

    def save_notice(self, notice: dict) -> None:
        self.saved_notices.append(notice)


DUE_DATE = date(2026, 2, 10)


def _base_account(balance: float = 500.0, status: str = "OVERDUE") -> _Account:
    return _Account(account_id="acc-1", current_balance=balance, status=status, due_date=DUE_DATE)


def _base_input(**overrides) -> ScheduleNoticeInput:
    defaults = dict(
        account_id="acc-1",
        evaluation_id="eval-1",
        risk_band=RiskBand.ALTA,
        scheduled_date=DUE_DATE + timedelta(days=3),  # dentro de ventana post_due de ALTA: [1..7]
        tone=Tone.NEUTRAL,
        subject="Recordatorio de pago",
        body_text="Cuerpo validado por ToneGuard.",
    )
    defaults.update(overrides)
    return ScheduleNoticeInput(**defaults)


def _run(policy_config: PolicyConfig, repo: _MockRepository, **input_overrides):
    tool = ScheduleNoticeTool(policy=policy_config, repository=repo)
    return tool.run(_base_input(**input_overrides))


def test_rejects_unknown_account(policy_config: PolicyConfig):
    repo = _MockRepository(accounts=[])
    output = _run(policy_config, repo)
    assert output.success is False
    assert output.rejection_code == ERR_UNKNOWN_ACCOUNT


def test_rejects_when_account_already_paid(policy_config: PolicyConfig):
    repo = _MockRepository(accounts=[_base_account(balance=0.0, status="PAID")])
    output = _run(policy_config, repo)
    assert output.success is False
    assert output.rejection_code == ERR_ALREADY_PAID


def test_rejects_when_payment_in_progress(policy_config: PolicyConfig):
    repo = _MockRepository(
        accounts=[_base_account()],
        pending_payments={
            "acc-1": [_PendingPayment(payment_id="p1", amount=100.0, payment_date=DUE_DATE, status="IN_PROCESS")]
        },
    )
    output = _run(policy_config, repo)
    assert output.success is False
    assert output.rejection_code == ERR_PAYMENT_IN_PROGRESS


def test_payment_in_progress_check_ignores_cleared_or_rejected(policy_config: PolicyConfig):
    repo = _MockRepository(
        accounts=[_base_account()],
        pending_payments={
            "acc-1": [
                _PendingPayment(payment_id="p1", amount=100.0, payment_date=DUE_DATE, status="CLEARED"),
                _PendingPayment(payment_id="p2", amount=50.0, payment_date=DUE_DATE, status="REJECTED"),
            ]
        },
    )
    output = _run(policy_config, repo)
    assert output.success is True
    assert output.rejection_code is None


def test_rejects_outside_window_too_far_after_due_date(policy_config: PolicyConfig):
    repo = _MockRepository(accounts=[_base_account()])
    # ALTA post_due permite [1..7] días después; 10 está fuera.
    output = _run(policy_config, repo, scheduled_date=DUE_DATE + timedelta(days=10))
    assert output.success is False
    assert output.rejection_code == ERR_OUTSIDE_WINDOW


def test_rejects_outside_window_when_phase_disallowed_for_band(policy_config: PolicyConfig):
    repo = _MockRepository(accounts=[_base_account()])
    # BAJA no permite contacto preventivo (allowed=false, ventana vacía).
    output = _run(
        policy_config,
        repo,
        risk_band=RiskBand.BAJA,
        scheduled_date=DUE_DATE - timedelta(days=2),
        tone=Tone.NEUTRAL,
    )
    assert output.success is False
    assert output.rejection_code == ERR_OUTSIDE_WINDOW


def test_rejects_when_scheduled_exactly_on_due_date(policy_config: PolicyConfig):
    repo = _MockRepository(accounts=[_base_account()])
    output = _run(policy_config, repo, scheduled_date=DUE_DATE)
    assert output.success is False
    assert output.rejection_code == ERR_OUTSIDE_WINDOW


def test_rejects_when_max_notices_exceeded(policy_config: PolicyConfig):
    # ALTA post_due permite max_notices=2.
    repo = _MockRepository(accounts=[_base_account()], notices_count=2)
    output = _run(policy_config, repo)
    assert output.success is False
    assert output.rejection_code == ERR_MAX_NOTICES_EXCEEDED


def test_rejects_when_min_separation_violated(policy_config: PolicyConfig):
    scheduled_date = DUE_DATE + timedelta(days=3)
    # ALTA post_due exige min_separation_days=2; último aviso fue hace 1 día.
    repo = _MockRepository(accounts=[_base_account()], last_notice_date=scheduled_date - timedelta(days=1))
    output = _run(policy_config, repo, scheduled_date=scheduled_date)
    assert output.success is False
    assert output.rejection_code == ERR_MIN_SEPARATION_VIOLATED


def test_allows_when_min_separation_exactly_met(policy_config: PolicyConfig):
    scheduled_date = DUE_DATE + timedelta(days=3)
    repo = _MockRepository(accounts=[_base_account()], last_notice_date=scheduled_date - timedelta(days=2))
    output = _run(policy_config, repo, scheduled_date=scheduled_date)
    assert output.success is True


def test_rejects_tone_not_allowed_for_band_phase(policy_config: PolicyConfig):
    # MODERADA post_due solo permite NEUTRAL (no FIRM).
    repo = _MockRepository(accounts=[_base_account()])
    output = _run(
        policy_config,
        repo,
        risk_band=RiskBand.MODERADA,
        scheduled_date=DUE_DATE + timedelta(days=2),
        tone=Tone.FIRM,
    )
    assert output.success is False
    assert output.rejection_code == ERR_INVALID_TONE_FOR_BAND


def test_rejects_firm_tone_before_due_date_even_if_band_allows_it(policy_config: PolicyConfig):
    # CRITICA preventivo permite PREVENTIVE/NEUTRAL, pero nunca FIRM antes del vencimiento.
    repo = _MockRepository(accounts=[_base_account()])
    output = _run(
        policy_config,
        repo,
        risk_band=RiskBand.CRITICA,
        scheduled_date=DUE_DATE - timedelta(days=3),
        tone=Tone.FIRM,
    )
    assert output.success is False
    assert output.rejection_code == ERR_INVALID_TONE_FOR_BAND


def test_approves_and_persists_notice_on_happy_path(policy_config: PolicyConfig):
    repo = _MockRepository(accounts=[_base_account()])
    output = _run(policy_config, repo)
    assert output.success is True
    assert output.status == "APPROVED"
    assert output.rejection_code is None
    assert output.notice_id is not None
    assert len(repo.saved_notices) == 1
    assert repo.saved_notices[0]["account_id"] == "acc-1"
    assert repo.saved_notices[0]["notice_id"] == output.notice_id


def test_rejection_does_not_persist_any_notice(policy_config: PolicyConfig):
    repo = _MockRepository(accounts=[_base_account(balance=0.0, status="PAID")])
    output = _run(policy_config, repo)
    assert output.success is False
    assert repo.saved_notices == []
