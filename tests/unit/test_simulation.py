"""Simulación determinista y benchmark agente vs. campaña fija (RF-17, RF-19, T024-T026)."""

from datetime import date
from pathlib import Path

import pytest

from src.analytics.model import RiskModel
from src.data.repository import AccountDTO
from src.policy.config import load_policy_config
from src.simulation.benchmark import run_benchmark
from src.simulation.engine import CustomerBehavior

ROOT = Path(__file__).resolve().parents[2]
START = date(2026, 10, 15)


def _account(due: date) -> AccountDTO:
    return AccountDTO(account_id="ACC-X", customer_id="CUST-X", credit_limit=5000, current_balance=1000,
                      minimum_payment=100, due_date=due, status="PENDING_PAYMENT")


def test_customer_behavior_is_deterministic_for_a_seed():
    due = date(2026, 10, 22)
    a = CustomerBehavior(seed=42).build_profile(_account(due), [], [], START)
    b = CustomerBehavior(seed=42).build_profile(_account(due), [], [], START)
    assert a == b


def test_overdue_account_at_start_never_pays_in_the_past():
    profile = CustomerBehavior(seed=1).build_profile(_account(date(2026, 10, 13)), [], [], START)
    assert profile.natural_pay_date is None or profile.natural_pay_date >= START


def test_a_reminder_never_delays_payment():
    behavior = CustomerBehavior(seed=5)
    due = date(2026, 10, 22)
    profile = behavior.build_profile(_account(due), [], [], START)
    for day in range(15, 22):
        before = behavior.pay_date(profile, [])
        after = behavior.pay_date(profile, [date(2026, 10, day)])
        assert before is None or (after is not None and after <= before)


def test_no_reaction_after_the_customer_already_paid():
    behavior = CustomerBehavior(seed=5)
    profile = behavior.build_profile(_account(date(2026, 10, 22)), [], [], START)
    paid = date(2026, 10, 16)
    assert behavior.apply_notice(profile, paid, date(2026, 10, 18)) == paid


@pytest.fixture(scope="module")
def small_benchmark():
    model = RiskModel.load(str(ROOT / "reports" / "risk_model.joblib"))
    policy = load_policy_config(ROOT / "config" / "politica.yaml")
    return model, policy


def test_benchmark_is_reproducible_and_never_contacts_in_clearing_payments(small_benchmark):
    model, policy = small_benchmark
    first = run_benchmark(model, policy, seed=42, customers=30, horizon_days=14)
    second = run_benchmark(model, policy, seed=42, customers=30, horizon_days=14)

    assert first.to_dict() == second.to_dict()
    assert first.agent.total_notices > 0 and first.fixed.total_notices > 0
    assert first.agent.notices_while_payment_in_process == 0
    assert first.agent.accounts == first.fixed.accounts == 30
