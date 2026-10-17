"""
MessageDrafter dual (RF-10, contracts/agent_protocols.md §1).

- DeterministicMessageDrafter: plantillas Jinja2 preaprobadas por tono (modo por defecto).
- LLMMessageDrafter: redacción asistida por un LLM compatible con OpenAI/Ollama; ante cualquier
  fallo o timeout (< 2 s) cae al modo determinista.
- compose_notice_message(): pipeline completo redactar -> ToneGuard -> fallback neutral ->
  personalización local.

Privacidad (Principio XI): `DraftContext` no contiene PII. El nombre del cliente se inyecta
localmente reemplazando NAME_PLACEHOLDER después de validar; nunca viaja al LLM.
"""

import json
import re
from datetime import date
from pathlib import Path
from typing import List, Optional, Protocol

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from pydantic import BaseModel, Field

from src.agent.llm import LLMClient, LLMUnavailableError
from src.agent.validator import ToneGuardValidator, ToneViolation
from src.domain.entities import Tone

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
NAME_PLACEHOLDER = "[NOMBRE_CLIENTE]"
DEFAULT_CUSTOMER_SALUTATION = "cliente"

TEMPLATE_BY_TONE = {
    Tone.NEUTRAL: "neutral.j2",
    Tone.PREVENTIVE: "preventive.j2",
    Tone.FIRM: "firm.j2",
}

VALIDATION_PASSED = "PASSED"
VALIDATION_FALLBACK = "FAILED_FALLBACK_APPLIED"


class DraftContext(BaseModel):
    # ATENCIÓN: No incluye nombres reales, documentos de identidad ni números de tarjeta
    client_reference: str = Field(description="Identificador anonimizado local")
    tone: Tone = Field(description="'NEUTRAL', 'PREVENTIVE', 'FIRM'")
    days_to_due: int = Field(description="Días para el vencimiento (negativo si ya venció)")
    amount_due: float = Field(description="Monto adeudado en formato numérico")
    due_date_str: str = Field(description="Fecha de vencimiento formateada")
    institution_name: str = Field(default="Entidad Financiera Demo")


class DraftedMessage(BaseModel):
    subject: str
    body_text: str
    used_llm: bool


class ValidatedMessage(BaseModel):
    """Mensaje listo para ScheduleNoticeTool (alimenta ContactNotice)."""
    subject: str
    body_text: str
    tone: Tone = Field(description="Tono final; NEUTRAL si se aplicó la plantilla de contingencia")
    used_llm: bool
    validation_status: str = Field(description="'PASSED' o 'FAILED_FALLBACK_APPLIED'")
    violations: List[ToneViolation] = Field(default_factory=list)


class MessageDrafter(Protocol):
    def draft(self, context: DraftContext) -> DraftedMessage:
        """Genera un borrador de mensaje adaptado al contexto y tono."""
        ...


def format_money(value: float) -> str:
    """Formato monetario local: $1.234.567,89"""
    formatted = f"{value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"${formatted}"


def format_due_date(value: date) -> str:
    """Fecha legible en español para inyectar en DraftContext.due_date_str."""
    months = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
              "agosto", "septiembre", "octubre", "noviembre", "diciembre")
    return f"{value.day} de {months[value.month - 1]} de {value.year}"


def due_phrase(days_to_due: int) -> str:
    if days_to_due > 1:
        return f"vence en {days_to_due} días"
    if days_to_due == 1:
        return "vence mañana"
    if days_to_due == 0:
        return "vence hoy"
    if days_to_due == -1:
        return "venció hace 1 día"
    return f"venció hace {-days_to_due} días"


def personalize(text: str, customer_name: Optional[str]) -> str:
    """Inyección local del nombre (nunca se envía al LLM)."""
    return text.replace(NAME_PLACEHOLDER, customer_name or DEFAULT_CUSTOMER_SALUTATION)


class DeterministicMessageDrafter:
    """Redacta con plantillas Jinja2 preaprobadas; 100% offline y reproducible."""

    def __init__(self, templates_dir: Path = TEMPLATES_DIR):
        self._env = Environment(
            loader=FileSystemLoader(str(templates_dir)),
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
            autoescape=False,
        )
        self._env.filters["money"] = format_money

    def draft(self, context: DraftContext) -> DraftedMessage:
        template = self._env.get_template(TEMPLATE_BY_TONE[context.tone])
        module = template.make_module({
            "customer_name": NAME_PLACEHOLDER,
            "amount_due": context.amount_due,
            "due_date_str": context.due_date_str,
            "due_phrase": due_phrase(context.days_to_due),
            "institution_name": context.institution_name,
        })
        return DraftedMessage(subject=module.subject, body_text=str(module).strip(), used_llm=False)


LLM_SYSTEM_PROMPT = (
    "Eres redactor de una entidad financiera. Redacta un recordatorio bancario formal en español. "
    "Tono: {tone_description}. No uses palabras intimidatorias, amenazas ni menciones legales; "
    "no menciones bandas de riesgo, scores, calificaciones internas ni morosidad; no califiques "
    "al cliente. Comienza el cuerpo con 'Estimado(a) " + NAME_PLACEHOLDER + ":' sin reemplazar "
    "ese marcador. Responde solo con JSON: {{\"subject\": \"...\", \"body\": \"...\"}}"
)

TONE_DESCRIPTIONS = {
    Tone.NEUTRAL: "neutral e informativo",
    Tone.PREVENTIVE: "cordial y preventivo, sin urgencia, invitando a contactar si hay dificultades",
    Tone.FIRM: "firme pero respetuoso, solicitando regularizar un pago ya vencido",
}

FEW_SHOT_EXAMPLE = {
    "subject": "Su próxima cuota con Entidad Financiera Demo",
    "body": (
        "Estimado(a) " + NAME_PLACEHOLDER + ":\n\nLe recordamos que su próxima cuota por $150.000,00 "
        "vence en 3 días (20 de octubre de 2026). Si prevé alguna dificultad, contáctenos y "
        "revisaremos juntos las alternativas.\n\nAtentamente,\nEntidad Financiera Demo"
    ),
}


class LLMMessageDrafter:
    """Redacción asistida por LLM con fallback determinista ante fallo o respuesta inválida."""

    def __init__(self, client: LLMClient, fallback: Optional[DeterministicMessageDrafter] = None):
        self._client = client
        self._fallback = fallback or DeterministicMessageDrafter()

    def draft(self, context: DraftContext) -> DraftedMessage:
        # Solo variables estructurales: sin client_reference ni datos personales.
        user_payload = {
            "dias_para_vencimiento": context.days_to_due,
            "situacion": due_phrase(context.days_to_due),
            "monto": format_money(context.amount_due),
            "fecha_vencimiento": context.due_date_str,
            "institucion": context.institution_name,
        }
        messages = [
            {"role": "system", "content": LLM_SYSTEM_PROMPT.format(
                tone_description=TONE_DESCRIPTIONS[context.tone])},
            {"role": "user", "content": json.dumps({
                "dias_para_vencimiento": 3, "situacion": "vence en 3 días", "monto": "$150.000,00",
                "fecha_vencimiento": "20 de octubre de 2026", "institucion": "Entidad Financiera Demo",
            }, ensure_ascii=False)},
            {"role": "assistant", "content": json.dumps(FEW_SHOT_EXAMPLE, ensure_ascii=False)},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ]
        try:
            parsed = _parse_llm_json(self._client.chat(messages))
            return DraftedMessage(subject=parsed["subject"], body_text=parsed["body"], used_llm=True)
        except (LLMUnavailableError, ValueError, KeyError, TypeError):
            return self._fallback.draft(context)


def _parse_llm_json(content: str) -> dict:
    """Extrae el primer objeto JSON de la respuesta (tolera bloques ```json)."""
    match = re.search(r"\{.*\}", content, re.DOTALL)
    if not match:
        raise ValueError("La respuesta del LLM no contiene JSON")
    data = json.loads(match.group(0))
    if not isinstance(data.get("subject"), str) or not isinstance(data.get("body"), str):
        raise ValueError("JSON del LLM sin 'subject'/'body' de tipo texto")
    return data


def build_drafter() -> MessageDrafter:
    """LLM si está configurado por entorno; de lo contrario, plantillas deterministas."""
    client = LLMClient.from_env()
    if client is None:
        return DeterministicMessageDrafter()
    return LLMMessageDrafter(client)


def compose_notice_message(
    context: DraftContext,
    customer_name: Optional[str] = None,
    drafter: Optional[MessageDrafter] = None,
    validator: Optional[ToneGuardValidator] = None,
) -> ValidatedMessage:
    """Redacta, valida con ToneGuard y, si falla, aplica la plantilla neutral estándar."""
    drafter = drafter or build_drafter()
    validator = validator or ToneGuardValidator()

    draft = drafter.draft(context)
    result = validator.validate(draft.subject, draft.body_text, context.days_to_due)
    if result.passed:
        return ValidatedMessage(
            subject=personalize(draft.subject, customer_name),
            body_text=personalize(draft.body_text, customer_name),
            tone=context.tone,
            used_llm=draft.used_llm,
            validation_status=VALIDATION_PASSED,
        )

    neutral_context = context.model_copy(update={"tone": Tone.NEUTRAL})
    fallback = DeterministicMessageDrafter().draft(neutral_context)
    fallback_result = validator.validate(fallback.subject, fallback.body_text, context.days_to_due)
    if not fallback_result.passed:
        # Una plantilla preaprobada que no pasa ToneGuard es un defecto de configuración.
        raise RuntimeError(f"La plantilla neutral no supera ToneGuard: {fallback_result.summary}")
    return ValidatedMessage(
        subject=personalize(fallback.subject, customer_name),
        body_text=personalize(fallback.body_text, customer_name),
        tone=Tone.NEUTRAL,
        used_llm=False,
        validation_status=VALIDATION_FALLBACK,
        violations=result.violations,
    )
