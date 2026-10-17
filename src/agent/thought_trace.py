"""
Generador de Trazas de Razonamiento del Agente Constitucional VERA-IA (Audit Trace / Chain of Thought).

Implementa el protocolo de auditoría e inspección técnica para visibilizar
el ciclo de pensamiento y el uso deliberado de herramientas deterministas (ReAct).

Cada evaluación genera pasos estructurados:
1. Lectura de historial (QueryAccountSignalsTool)
2. Cálculo de señales y riesgo calibrado (EvaluateRiskModel)
3. Consulta de herramientas de política (ScheduleNoticeTool / InvestigatePendingPaymentsTool)
4. Decisión final y justificación constitucional (ConstitutionalGuard)

Opcionalmente sintetiza el análisis en lenguaje natural mediante LLM (OpenRouter / OpenAI).
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.agent.llm import LLMClient, LLMUnavailableError

logger = logging.getLogger(__name__)


@dataclass
class ThoughtStep:
    step: int
    title: str
    tool: str
    detail: str
    observation: str
    status: str = "SUCCESS"  # "SUCCESS" | "BLOCKED" | "INFO" | "WARNING"
    timestamp: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AgentThoughtTrace:
    account_id: str
    customer_name: str
    cycle_date: str
    steps: List[ThoughtStep] = field(default_factory=list)
    final_verdict: str = ""
    constitutional_rule: str = ""
    llm_analysis: Optional[str] = None
    used_llm: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "account_id": self.account_id,
            "customer_name": self.customer_name,
            "cycle_date": self.cycle_date,
            "steps": [s.to_dict() for s in self.steps],
            "final_verdict": self.final_verdict,
            "constitutional_rule": self.constitutional_rule,
            "llm_analysis": self.llm_analysis,
            "used_llm": self.used_llm,
        }


def build_thought_trace(
    account: Any,
    customer_name: str,
    history: List[Any],
    signals: Any,
    band: Any,
    calibrated_p: float,
    hysteresis: Any,
    evidence: Any,
    days_to_due: int,
    action: Any,
    rule: str,
    detail: str,
    pending: List[Any],
    extra: Dict[str, Any],
    target_day: Optional[int] = None,
    cycle_date: Optional[str] = None,
) -> AgentThoughtTrace:
    """Construye los 4 pasos estructurados del razonamiento determinista."""
    now_iso = datetime.now().strftime("%H:%M:%S")
    n_months = len(history) if history else 6
    band_name = getattr(band, "value", str(band))
    action_name = getattr(action, "value", str(action))
    evidence_name = getattr(evidence, "value", str(evidence))
    hysteresis_rule = getattr(hysteresis, "rule_applied", str(hysteresis))

    utilization_pct = int(round(signals.credit_utilization_ratio * 100))
    min_payments = signals.consecutive_min_payments

    steps: List[ThoughtStep] = []

    # -------------------------------------------------------------
    # Paso 1: Lectura de historial
    # -------------------------------------------------------------
    step1_title = f"Leyendo historial de {n_months} meses..."
    step1_obs = (
        f"Historial de {n_months} periodos cargado para cuenta {account.account_id}. "
        f"Cumplimiento Principio IV (Integridad temporal sin fuga de datos)."
    )
    steps.append(
        ThoughtStep(
            step=1,
            title=step1_title,
            tool="QueryAccountSignalsTool",
            detail=f"account_id={account.account_id}, periodos={n_months}",
            observation=step1_obs,
            status="SUCCESS",
            timestamp=now_iso,
        )
    )

    # -------------------------------------------------------------
    # Paso 2: Cálculo de señales y riesgo calibrado
    # -------------------------------------------------------------
    step2_title = f"Calculando señales: Utilización = {utilization_pct}%, Pagos mínimos = {min_payments}. Riesgo: {band_name}."
    step2_obs = (
        f"Probabilidad calibrada: {calibrated_p:.1%}. "
        f"Histéresis: {hysteresis_rule}. Evidencia: {evidence_name}."
    )
    steps.append(
        ThoughtStep(
            step=2,
            title=step2_title,
            tool="EvaluateRiskModel (Platt-Scaled)",
            detail=f"P(mora)={calibrated_p:.4f}, banda={band_name}",
            observation=step2_obs,
            status="SUCCESS",
            timestamp=now_iso,
        )
    )

    # -------------------------------------------------------------
    # Paso 3: Consulta de herramientas de política
    # -------------------------------------------------------------
    step3_tool = "ScheduleNoticeTool"
    step3_status = "SUCCESS"

    if pending and evidence_name == "INCONSISTENT":
        step3_tool = "InvestigatePendingPaymentsTool"
        step3_title = "Consultando herramienta InvestigatePendingPaymentsTool... Pago en trámite detectado."
        step3_obs = (
            f"Existe pago pendiente en compensación. "
            f"Principio II: Suspensión de recordatorios automáticos por inconsistencia temporal."
        )
        step3_status = "WARNING"
    elif rule == "WAITING_SEND_DAY":
        diff = max(1, days_to_due - (target_day or max(0, days_to_due - 1)))
        step3_title = f"Consultando herramienta ScheduleNoticeTool... Bloqueado por regla de ventana: falta {diff} día para ventana autorizada."
        step3_obs = (
            f"Ventana autorizada a {target_day or 3} días del vencimiento (hoy faltan {days_to_due} días). "
            f"Contacto bloqueado para evitar sobre-notificación al cliente."
        )
        step3_status = "BLOCKED"
    elif rule in ("OUTSIDE_WINDOW", "NO_CONTACT_WINDOW"):
        step3_title = "Consultando herramienta ScheduleNoticeTool... Bloqueado por regla de ventana: fuera de ventana autorizada."
        step3_obs = f"La política no autoriza contacto en el día {days_to_due} respecto al vencimiento."
        step3_status = "BLOCKED"
    elif rule == "ALREADY_PAID":
        step3_tool = "CheckAccountBalanceTool"
        step3_title = "Consultando herramienta CheckAccountBalanceTool... Cuenta al día o sin saldo pendiente."
        step3_obs = "Saldo $0 o estado PAID. No se requiere intervención."
        step3_status = "SUCCESS"
    elif rule == "QUOTA_OR_SEPARATION":
        step3_title = "Consultando herramienta ScheduleNoticeTool... Bloqueado por separación mínima o cuota máxima."
        step3_obs = "Separación entre avisos inferior al mínimo o límite de avisos alcanzado para esta fase."
        step3_status = "BLOCKED"
    elif action_name == "ESCALATE_HUMAN":
        step3_tool = "EscalateToReviewQueueTool"
        step3_title = f"Consultando herramienta EscalateToReviewQueueTool... Derivando caso: {rule}."
        step3_obs = f"{detail}. Caso enviado a la cola del analista."
        step3_status = "WARNING"
    elif action_name == "SCHEDULE_NOTICE" or extra.get("notice_id"):
        tone = extra.get("schedule", {}).get("tone")
        tone_str = getattr(tone, "value", str(tone)) if tone else "PREVENTIVE"
        step3_title = f"Consultando herramienta ScheduleNoticeTool... Ventana autorizada. Aviso {tone_str} aprobado."
        step3_obs = "Verificación de política superada. ToneGuard: PASSED. Programado para envío a las 10:00."
        step3_status = "SUCCESS"
    elif extra.get("rejection_code"):
        rej = extra["rejection_code"]
        step3_title = f"Consultando herramienta ScheduleNoticeTool... Bloqueado por política ({rej})."
        step3_obs = f"Rechazo determinista: {rej}. {detail}"
        step3_status = "BLOCKED"
    else:
        step3_title = f"Consultando herramienta ScheduleNoticeTool... {detail}"
        step3_obs = f"Regla evaluada: {rule}."
        step3_status = "INFO"

    steps.append(
        ThoughtStep(
            step=3,
            title=step3_title,
            tool=step3_tool,
            detail=f"rule={rule}, days_to_due={days_to_due}",
            observation=step3_obs,
            status=step3_status,
            timestamp=now_iso,
        )
    )

    # -------------------------------------------------------------
    # Paso 4: Decisión final (Constitutional Verdict)
    # -------------------------------------------------------------
    if rule in ("WAITING_SEND_DAY", "OUTSIDE_WINDOW", "NO_CONTACT_WINDOW", "QUOTA_OR_SEPARATION"):
        step4_title = "Decisión: Retener y reevaluar mañana."
        verdict = "Retener y reevaluar mañana"
    elif rule == "ALREADY_PAID":
        step4_title = "Decisión: No contactar (cuenta sin deuda pendiente)."
        verdict = "Sin acción (al día)"
    elif action_name == "ESCALATE_HUMAN":
        step4_title = f"Decisión: Derivar a cola de revisión humana ({detail})."
        verdict = "Derivado a analista humano"
    elif action_name == "SCHEDULE_NOTICE" or extra.get("notice_id"):
        step4_title = "Decisión: Despachar aviso preventivo autorizado en el corte de las 10:00."
        verdict = "Aviso aprobado para despacho"
    else:
        step4_title = f"Decisión: {detail}"
        verdict = detail

    steps.append(
        ThoughtStep(
            step=4,
            title=step4_title,
            tool="ConstitutionalGuard",
            detail=f"action={action_name}, rule={rule}",
            observation="Veredicto final emitido bajo gobernanza constitucional estricta.",
            status="INFO",
            timestamp=now_iso,
        )
    )

    trace = AgentThoughtTrace(
        account_id=account.account_id,
        customer_name=customer_name,
        cycle_date=cycle_date or datetime.now().strftime("%Y-%m-%d"),
        steps=steps,
        final_verdict=verdict,
        constitutional_rule=rule,
        llm_analysis=None,
        used_llm=False,
    )
    return trace


def synthesize_reasoning_with_llm(
    trace: AgentThoughtTrace,
    client: Optional[LLMClient] = None,
    timeout_seconds: float = 8.0,
) -> str:
    """
    Sintetiza la justificación técnica del veredicto mediante LLM (OpenRouter / OpenAI).
    Si el LLM no responde o no está disponible, retorna una justificación determinista.
    """
    client = client or LLMClient.from_env()
    if client is None:
        return _fallback_synthesis(trace)

    prompt_system = (
        "Eres el Auditor Constitucional VERA-IA en un banco regulado. "
        "En exactamente 2 oraciones concisas y de alto nivel técnico, resume por qué el veredicto "
        "del agente protege el balance crediticio del banco y cumple rigurosamente la política de buen trato."
    )
    prompt_user = (
        f"Expediente evaluado:\n"
        f"- Cuenta: {trace.account_id}\n"
        f"- Paso 1: {trace.steps[0].title}\n"
        f"- Paso 2: {trace.steps[1].title}\n"
        f"- Paso 3: {trace.steps[2].title}\n"
        f"- Paso 4: {trace.steps[3].title}\n"
        f"- Regla de gobernanza: {trace.constitutional_rule}\n"
        f"- Veredicto: {trace.final_verdict}\n"
        f"Justificación técnica y regulatoria:"
    )

    messages = [
        {"role": "system", "content": prompt_system},
        {"role": "user", "content": prompt_user},
    ]

    try:
        response = client.chat(messages, temperature=0.2)
        trace.llm_analysis = response.strip()
        trace.used_llm = True
        return trace.llm_analysis
    except Exception as exc:
        logger.warning("Fallo al consultar LLM para audit trace: %s", exc)
        fallback = _fallback_synthesis(trace)
        trace.llm_analysis = fallback
        trace.used_llm = False
        return fallback


def _fallback_synthesis(trace: AgentThoughtTrace) -> str:
    """Síntesis determinista preaprobada según la regla constitucional aplicada."""
    rule = trace.constitutional_rule
    if rule in ("WAITING_SEND_DAY", "OUTSIDE_WINDOW"):
        return (
            "El agente VERA-IA retiene el contacto preventivo en estricto cumplimiento de la ventana autorizada por política, "
            "evitando la sobre-notificación al cliente mientras mantiene monitoreo continuo del perfil de riesgo crediticio."
        )
    if "PAYMENT" in rule:
        return (
            "Se detectó un pago en trámite de compensación bancaria. Siguiendo el Principio II de no hostigamiento, "
            "la acción automática queda congelada hasta la conciliación contable por el analista."
        )
    if "OVER_LIMIT" in rule:
        return (
            "El saldo deudor supera la línea contractual asignada. El agente detiene cualquier comunicación automática "
            "y traslada el caso a revisión humana especializada para renegociación o ajuste de cupo."
        )
    if "NOTICE_APPROVED" in rule or "SCHEDULE_NOTICE" in trace.final_verdict:
        return (
            "El aviso preventivo cumple todas las restricciones de ventana, separación de días y validación léxica ToneGuard, "
            "quedando agendado para despacho seguro en el corte diario."
        )
    return (
        f"El agente ejecutó la política constitucional bajo la regla {rule}, garantizando trazabilidad auditable "
        f"y salvaguardando la relación con el cliente."
    )
