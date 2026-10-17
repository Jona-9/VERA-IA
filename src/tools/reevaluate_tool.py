"""
ReevaluateClientTool: corrección de pago por el analista y reevaluación inmediata (RF-13).

Contrato en `sdd/specs/001-early-collection-agent/contracts/tools_contract.md` §3. Tras una
corrección, el agente vuelve a evaluar solo a ese cliente con los datos nuevos y anula los
avisos aprobados que ya no correspondan; el aviso, si procede, vuelve a pasar por
`ScheduleNoticeTool`.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel

from src.agent.orchestrator import DailyCycleOrchestrator
from src.domain.entities import ActionType


ACTION_TEXT = {
    "NO_ACTION": "sin acción",
    "SCHEDULE_NOTICE": "aviso programado",
    "INVESTIGATE": "investigar",
    "ESCALATE_HUMAN": "derivar a revisión",
}


class ReevaluateClientInput(BaseModel):
    account_id: str
    cutoff_date: date
    reason: str


class ReevaluateClientOutput(BaseModel):
    account_id: str
    new_risk_band: str
    new_action: str
    decision_updated: bool
    summary: str


class ReevaluateClientTool:
    def __init__(self, orchestrator: DailyCycleOrchestrator):
        self._orchestrator = orchestrator
        self._repo = orchestrator.repo

    def run(self, input_data: ReevaluateClientInput) -> ReevaluateClientOutput:
        repo = self._repo
        account = repo.get_account(input_data.account_id)
        if account is None:
            raise ValueError(f"No existe la cuenta {input_data.account_id}")

        previous = next(
            (e for e in repo.get_evaluations(input_data.account_id)
             if e["evaluation_date"][:10] == input_data.cutoff_date.isoformat()),
            None,
        )
        cancelled = self._orchestrator.cancel_notices(
            input_data.account_id, input_data.cutoff_date,
            f"CANCELADO tras reevaluación: {input_data.reason}",
        )
        decision = self._orchestrator.evaluate_account(account, input_data.cutoff_date)
        new_band = decision.evaluation["risk_band"].value
        new_action = decision.action.value
        updated = previous is None or previous["action_type"] != new_action or cancelled > 0

        parts = [f"Nueva decisión: {ACTION_TEXT.get(new_action, new_action)}. {decision.detail}"]
        if cancelled:
            parts.append(f"Se anuló {cancelled} aviso pendiente.")
        if decision.action == ActionType.SCHEDULE_NOTICE:
            parts.append("Se programó un aviso nuevo.")
        return ReevaluateClientOutput(
            account_id=input_data.account_id,
            new_risk_band=new_band,
            new_action=new_action,
            decision_updated=updated,
            summary=" ".join(parts),
        )

    def correct_payment_and_reevaluate(
        self,
        case_id: str,
        account_id: str,
        cutoff_date: date,
        actor: str,
        notes: str,
        payment_date: Optional[date] = None,
        amount: Optional[float] = None,
    ) -> ReevaluateClientOutput:
        """Registra el pago confirmado (si lo hay), cierra el caso y reevalúa al cliente."""
        if amount and payment_date:
            self._repo.update_payment_record(account_id, payment_date, amount, actor)
            reason = f"Pago confirmado por {actor}: {amount:,.2f} el {payment_date.isoformat()}."
        else:
            reason = f"Sin pago registrado; {actor} autoriza seguir la política regular."
        self._repo.resolve_review_case(case_id, actor, notes or reason)
        return self.run(ReevaluateClientInput(account_id=account_id, cutoff_date=cutoff_date, reason=reason))
