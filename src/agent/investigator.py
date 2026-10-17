"""
InconsistencyInvestigator dual (RF-09, contracts/agent_protocols.md §3).

- DeterministicInvestigator: decide con reglas explícitas si una inconsistencia se explica por
  un pago en proceso de acreditación.
- LLMInconsistencyInvestigator: reutiliza la decisión determinista (Principio III: la IA no
  decide) y solo redacta una nota de derivación más detallada para el analista humano.

Integridad temporal (Principio IV): los pagos con fecha posterior a `cutoff_date` se ignoran.
"""

import json
from datetime import date
from typing import Any, Dict, List, Optional, Protocol

from pydantic import BaseModel, Field, field_validator

from src.agent.llm import LLMClient, LLMUnavailableError

ACTION_WAIT_FOR_CLEARING = "WAIT_FOR_CLEARING"
ACTION_ESCALATE_HUMAN = "ESCALATE_HUMAN"
ACTION_PROCEED = "PROCEED"

STATUS_IN_PROCESS = "IN_PROCESS"
STATUS_REJECTED = "REJECTED"

DEFAULT_TOLERANCE_DAYS = 2  # politica.yaml: evidence_rules.unreflected_payment_tolerance_days

HYPOTHESIS_PENDING_CLEARING = "Pago en proceso de acreditación bancaria (demora interbancaria de 48h)"


class InvestigationContext(BaseModel):
    account_id: str
    billed_amount: float
    current_balance: float
    days_past_due: int
    pending_payments: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Pagos en trámite: amount, payment_date (o reported_date), status",
    )
    discrepancy_description: str
    cutoff_date: date = Field(description="Fecha de corte; no se usa información posterior")
    minimum_payment: Optional[float] = Field(
        default=None, description="Pago mínimo exigible; si falta se exige el monto facturado"
    )
    tolerance_days: int = Field(default=DEFAULT_TOLERANCE_DAYS, ge=0)

    @field_validator("pending_payments", mode="before")
    @classmethod
    def _models_to_dicts(cls, value):
        # Acepta entidades PendingPayment o PendingPaymentItem además de diccionarios.
        return [p.model_dump() if isinstance(p, BaseModel) else p for p in value or []]


class InvestigationResult(BaseModel):
    hypothesis: str
    verified: bool
    recommended_action: str  # 'WAIT_FOR_CLEARING', 'ESCALATE_HUMAN', 'PROCEED'
    explanation: str


class InconsistencyInvestigator(Protocol):
    def investigate(self, context: InvestigationContext) -> InvestigationResult:
        """Formula y evalúa una hipótesis sobre la inconsistencia observada."""
        ...


def _payment_date(payment: Dict[str, Any]) -> Optional[date]:
    value = payment.get("payment_date") or payment.get("reported_date")
    if isinstance(value, str):
        return date.fromisoformat(value)
    return value


class DeterministicInvestigator:
    """Reglas auditables para pagos no reflejados."""

    def investigate(self, context: InvestigationContext) -> InvestigationResult:
        required = context.minimum_payment if context.minimum_payment is not None else context.billed_amount
        observed = [p for p in context.pending_payments
                    if (d := _payment_date(p)) is not None and d <= context.cutoff_date]

        in_process = [p for p in observed if p.get("status", STATUS_IN_PROCESS) == STATUS_IN_PROCESS]
        clearing = [
            p for p in in_process
            if float(p.get("amount", 0)) >= required
            and (context.cutoff_date - _payment_date(p)).days <= context.tolerance_days
        ]
        if clearing:
            payment = max(clearing, key=lambda p: _payment_date(p))
            return InvestigationResult(
                hypothesis=HYPOTHESIS_PENDING_CLEARING,
                verified=True,
                recommended_action=ACTION_WAIT_FOR_CLEARING,
                explanation=(
                    f"Pago en trámite por {float(payment['amount']):.2f} emitido el "
                    f"{_payment_date(payment).isoformat()} (>= mínimo exigible {required:.2f}, "
                    f"dentro de la tolerancia de {context.tolerance_days} días al corte "
                    f"{context.cutoff_date.isoformat()}). Se suspende el contacto hasta su acreditación."
                ),
            )

        if observed and all(p.get("status") == STATUS_REJECTED for p in observed):
            return InvestigationResult(
                hypothesis="El pago reportado fue rechazado; no existe pago en tránsito",
                verified=True,
                recommended_action=ACTION_PROCEED,
                explanation=(
                    f"{len(observed)} pago(s) reportado(s) con estado REJECTED a la fecha de corte "
                    f"{context.cutoff_date.isoformat()}. La discrepancia queda explicada y aplica "
                    "la política regular."
                ),
            )

        return InvestigationResult(
            hypothesis="Inconsistencia no explicada por pagos en trámite",
            verified=False,
            recommended_action=ACTION_ESCALATE_HUMAN,
            explanation=self._escalation_note(context, required, in_process),
        )

    @staticmethod
    def _escalation_note(context: InvestigationContext, required: float,
                         in_process: List[Dict[str, Any]]) -> str:
        facts = [
            f"Discrepancia: {context.discrepancy_description}",
            f"Facturado {context.billed_amount:.2f}, saldo {context.current_balance:.2f}, "
            f"mínimo exigible {required:.2f}, días de atraso {context.days_past_due}",
        ]
        if not in_process:
            facts.append("Sin pagos en trámite a la fecha de corte")
        for p in in_process:
            pdate = _payment_date(p)
            reasons = []
            if float(p.get("amount", 0)) < required:
                reasons.append("monto inferior al mínimo")
            if (context.cutoff_date - pdate).days > context.tolerance_days:
                reasons.append(f"excede la tolerancia de {context.tolerance_days} días")
            facts.append(f"Pago en trámite {float(p.get('amount', 0)):.2f} del {pdate.isoformat()}: "
                         + ", ".join(reasons))
        return "Derivado a revisión humana. " + ". ".join(facts) + "."


class LLMInconsistencyInvestigator:
    """Enriquece la nota de derivación con un LLM; la decisión siempre es determinista."""

    def __init__(self, client: LLMClient, base: Optional[DeterministicInvestigator] = None):
        self._client = client
        self._base = base or DeterministicInvestigator()

    def investigate(self, context: InvestigationContext) -> InvestigationResult:
        result = self._base.investigate(context)
        if result.recommended_action != ACTION_ESCALATE_HUMAN:
            return result
        # Contexto anonimizado: sin account_id ni identificadores de pago.
        facts = {
            "monto_facturado": context.billed_amount,
            "saldo_actual": context.current_balance,
            "dias_atraso": context.days_past_due,
            "discrepancia": context.discrepancy_description,
            "pagos_en_tramite": [
                {"monto": float(p.get("amount", 0)),
                 "dias_desde_emision": (context.cutoff_date - _payment_date(p)).days,
                 "estado": p.get("status", STATUS_IN_PROCESS)}
                for p in context.pending_payments
                if _payment_date(p) is not None and _payment_date(p) <= context.cutoff_date
            ],
            "hallazgo_reglas": result.explanation,
        }
        messages = [
            {"role": "system", "content": (
                "Eres asistente de un analista de cobranza. Resume en máximo 4 frases, en español, "
                "los hechos observados y qué debería verificar el analista. No tomes decisiones, "
                "no recomiendes contactar al cliente y no califiques al cliente."
            )},
            {"role": "user", "content": json.dumps(facts, ensure_ascii=False)},
        ]
        try:
            note = self._client.chat(messages).strip()
        except LLMUnavailableError:
            return result
        if not note:
            return result
        return result.model_copy(update={"explanation": f"{result.explanation}\nNota asistida: {note}"})


def build_investigator() -> InconsistencyInvestigator:
    """LLM si está configurado por entorno; de lo contrario, reglas deterministas."""
    client = LLMClient.from_env()
    if client is None:
        return DeterministicInvestigator()
    return LLMInconsistencyInvestigator(client)
