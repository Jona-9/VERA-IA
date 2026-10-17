"""Ciclo diario: corte 09:00, despacho 10:00, retención de casos sin revisar y reevaluación (T018/T020/T022)."""

import time
from datetime import date
from pathlib import Path

import pytest

from src.agent.orchestrator import DailyCycleOrchestrator, NullDispatcher
from src.analytics.model import RiskModel
from src.data.generator import PortfolioGenerator
from src.domain.entities import ActionType
from src.policy.config import load_policy_config
from src.tools.reevaluate_tool import ReevaluateClientInput, ReevaluateClientTool

ROOT = Path(__file__).resolve().parents[2]
CUTOFF = date(2026, 10, 15)


@pytest.fixture(scope="module")
def model():
    return RiskModel.load(str(ROOT / "reports" / "risk_model.joblib"))


@pytest.fixture(scope="module")
def policy():
    return load_policy_config(ROOT / "config" / "politica.yaml")


@pytest.fixture()
def repo(tmp_path):
    return PortfolioGenerator(seed=42, cutoff_date=CUTOFF).populate_database(str(tmp_path / "cycle.db"), 60)


@pytest.fixture()
def orchestrator(repo, model, policy):
    return DailyCycleOrchestrator(repo, model, policy)


def test_pending_payment_suspends_contact_and_opens_review_case(repo, orchestrator):
    report = orchestrator.run_evaluation(CUTOFF)

    in_clearing = [d for d in report.decisions if d.rule == "PAYMENT_IN_CLEARING"]
    assert in_clearing, "la cartera semilla incluye pagos en trámite"
    pending_cases = {c["account_id"] for c in repo.get_review_queue()}
    for decision in in_clearing:
        assert decision.notice_id is None
        assert decision.account_id in pending_cases


def test_unreviewed_cases_are_not_dispatched(repo, orchestrator):
    orchestrator.run_evaluation(CUTOFF)
    case = repo.get_review_queue()[0]
    # Un aviso aprobado para una cuenta con caso sin revisar a las 09:00 debe quedar retenido.
    repo.save_notice({
        "notice_id": "N-HELD", "account_id": case["account_id"], "evaluation_id": case["evaluation_id"],
        "scheduled_date": CUTOFF, "tone": "NEUTRAL", "subject": "Asunto", "body_text": "Texto", "status": "APPROVED",
    })

    report = orchestrator.close_review_and_dispatch(CUTOFF, NullDispatcher())

    assert "N-HELD" in report.held and "N-HELD" not in report.sent
    held = next(n for n in repo.get_notices() if n["notice_id"] == "N-HELD")
    assert held["status"] == "REJECTED" and "RETENIDO" in held["rejection_reason"]


def test_only_approved_notices_of_the_day_are_sent(repo, orchestrator):
    cycle = orchestrator.run_evaluation(CUTOFF)
    approved = {d.notice_id for d in cycle.decisions if d.notice_id}
    assert approved

    report = orchestrator.close_review_and_dispatch(CUTOFF, NullDispatcher())

    assert set(report.sent) == approved - set(report.held)
    statuses = {n["status"] for n in repo.get_notices() if n["notice_id"] in report.sent}
    assert statuses == {"DISPATCHED"}


def test_rerunning_the_same_day_does_not_duplicate_notices_or_cases(repo, orchestrator):
    orchestrator.run_evaluation(CUTOFF)
    notices, cases = len(repo.get_notices()), len(repo.get_review_queue())

    orchestrator.run_evaluation(CUTOFF)

    assert len(repo.get_notices()) == notices
    assert len(repo.get_review_queue()) == cases


def test_payment_correction_cancels_the_pending_notice(repo, orchestrator):
    cycle = orchestrator.run_evaluation(CUTOFF)
    target = next(d for d in cycle.decisions if d.notice_id)
    account = repo.get_account(target.account_id)

    repo.update_payment_record(target.account_id, CUTOFF, account.current_balance, "ANALISTA")
    output = ReevaluateClientTool(orchestrator).run(ReevaluateClientInput(
        account_id=target.account_id, cutoff_date=CUTOFF, reason="Pago confirmado",
    ))

    notice = next(n for n in repo.get_notices(target.account_id) if n["notice_id"] == target.notice_id)
    assert notice["status"] == "REJECTED"
    assert output.new_action == ActionType.NO_ACTION.value
    assert output.decision_updated


def test_analyst_resolution_is_audited_and_not_reopened(repo, orchestrator):
    orchestrator.run_evaluation(CUTOFF)
    case = repo.get_review_queue()[0]

    ReevaluateClientTool(orchestrator).correct_payment_and_reevaluate(
        case_id=case["case_id"], account_id=case["account_id"], cutoff_date=CUTOFF,
        actor="analista", notes="Confirmado por banca", payment_date=CUTOFF, amount=100.0,
    )
    orchestrator.run_evaluation(CUTOFF)

    assert case["case_id"] not in {c["case_id"] for c in repo.get_review_queue()}
    assert repo.get_audit_logs(case["account_id"], "REVIEW_RESOLVED")
    assert repo.get_audit_logs(case["account_id"], "CORRECTION")


def test_evaluation_cycle_for_100_customers_is_under_10_seconds(tmp_path, model, policy):
    repo = PortfolioGenerator(seed=42, cutoff_date=CUTOFF).populate_database(str(tmp_path / "big.db"), 100)
    started = time.perf_counter()
    DailyCycleOrchestrator(repo, model, policy).run_evaluation(CUTOFF)
    assert time.perf_counter() - started < 10
