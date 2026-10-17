"""Pruebas del investigador de inconsistencias de pago (T016, RF-09)."""

from datetime import date

from src.agent.investigator import (
    ACTION_ESCALATE_HUMAN,
    ACTION_PROCEED,
    ACTION_WAIT_FOR_CLEARING,
    HYPOTHESIS_PENDING_CLEARING,
    DeterministicInvestigator,
    InvestigationContext,
    LLMInconsistencyInvestigator,
)
from src.agent.llm import LLMUnavailableError
from src.domain.entities import PendingPayment

CUTOFF = date(2026, 10, 15)


def make_context(pending, minimum_payment=100.0, **overrides):
    data = dict(
        account_id="ACC-001",
        billed_amount=500.0,
        current_balance=500.0,
        days_past_due=1,
        pending_payments=pending,
        discrepancy_description="Cliente reporta pago no reflejado",
        cutoff_date=CUTOFF,
        minimum_payment=minimum_payment,
    )
    data.update(overrides)
    return InvestigationContext(**data)


def payment(amount, payment_date, status="IN_PROCESS"):
    return {"payment_id": "P1", "amount": amount, "payment_date": payment_date, "status": status}


class StubLLMClient:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls = response, error, []

    def chat(self, messages, temperature=0.2):
        self.calls.append(messages)
        if self.error:
            raise self.error
        return self.response


def test_payment_in_clearing_window_waits():
    result = DeterministicInvestigator().investigate(make_context([payment(150.0, date(2026, 10, 14))]))
    assert result.verified
    assert result.recommended_action == ACTION_WAIT_FOR_CLEARING
    assert result.hypothesis == HYPOTHESIS_PENDING_CLEARING


def test_accepts_pending_payment_entities():
    entity = PendingPayment(payment_id="P9", account_id="ACC-001", amount=200.0,
                            payment_date=date(2026, 10, 13))
    result = DeterministicInvestigator().investigate(make_context([entity]))
    assert result.recommended_action == ACTION_WAIT_FOR_CLEARING


def test_payment_at_exact_tolerance_limit_waits():
    result = DeterministicInvestigator().investigate(make_context([payment(100.0, date(2026, 10, 13))]))
    assert result.recommended_action == ACTION_WAIT_FOR_CLEARING


def test_payment_outside_tolerance_escalates():
    result = DeterministicInvestigator().investigate(make_context([payment(150.0, date(2026, 10, 10))]))
    assert not result.verified
    assert result.recommended_action == ACTION_ESCALATE_HUMAN
    assert "excede la tolerancia" in result.explanation


def test_partial_payment_below_minimum_escalates():
    result = DeterministicInvestigator().investigate(make_context([payment(50.0, date(2026, 10, 14))]))
    assert result.recommended_action == ACTION_ESCALATE_HUMAN
    assert "inferior al mínimo" in result.explanation


def test_without_minimum_requires_billed_amount():
    ctx = make_context([payment(150.0, date(2026, 10, 14))], minimum_payment=None)
    assert DeterministicInvestigator().investigate(ctx).recommended_action == ACTION_ESCALATE_HUMAN


def test_no_pending_payments_escalates():
    result = DeterministicInvestigator().investigate(make_context([]))
    assert result.recommended_action == ACTION_ESCALATE_HUMAN
    assert "Sin pagos en trámite" in result.explanation


def test_future_payments_are_ignored_no_lookahead():
    result = DeterministicInvestigator().investigate(make_context([payment(500.0, date(2026, 10, 16))]))
    assert result.recommended_action == ACTION_ESCALATE_HUMAN


def test_rejected_payment_explains_discrepancy():
    result = DeterministicInvestigator().investigate(
        make_context([payment(150.0, date(2026, 10, 14), status="REJECTED")]))
    assert result.verified
    assert result.recommended_action == ACTION_PROCEED


def test_llm_enriches_note_without_changing_decision_or_leaking_ids():
    client = StubLLMClient(response="El analista debe verificar el extracto bancario.")
    ctx = make_context([payment(50.0, date(2026, 10, 14))])
    result = LLMInconsistencyInvestigator(client).investigate(ctx)
    assert result.recommended_action == ACTION_ESCALATE_HUMAN
    assert "Nota asistida" in result.explanation
    sent = str(client.calls)
    assert "ACC-001" not in sent and "P1" not in sent


def test_llm_not_called_when_rules_resolve_case():
    client = StubLLMClient(response="x")
    result = LLMInconsistencyInvestigator(client).investigate(make_context([payment(150.0, date(2026, 10, 14))]))
    assert result.recommended_action == ACTION_WAIT_FOR_CLEARING
    assert client.calls == []


def test_llm_failure_keeps_deterministic_result():
    client = StubLLMClient(error=LLMUnavailableError("timeout"))
    ctx = make_context([])
    assert LLMInconsistencyInvestigator(client).investigate(ctx) == DeterministicInvestigator().investigate(ctx)
