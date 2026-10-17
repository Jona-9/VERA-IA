"""Pruebas de ToneGuardValidator y del pipeline de redacción con fallback (T012, RF-10)."""

import pytest

from src.agent.drafter import (
    NAME_PLACEHOLDER,
    VALIDATION_FALLBACK,
    VALIDATION_PASSED,
    DeterministicMessageDrafter,
    DraftContext,
    DraftedMessage,
    LLMMessageDrafter,
    compose_notice_message,
    due_phrase,
    format_money,
)
from src.agent.llm import LLMUnavailableError
from src.agent.validator import ToneGuardValidator, ToneRule
from src.domain.entities import Tone

SAFE_BODY = "Estimado(a) cliente:\n\nLe recordamos que su cuota vence en 3 días."


@pytest.fixture
def validator():
    return ToneGuardValidator()


def make_context(tone=Tone.PREVENTIVE, days_to_due=3):
    return DraftContext(
        client_reference="REF-001",
        tone=tone,
        days_to_due=days_to_due,
        amount_due=150000.0,
        due_date_str="20 de octubre de 2026",
    )


class StubDrafter:
    def __init__(self, subject, body):
        self.message = DraftedMessage(subject=subject, body_text=body, used_llm=True)

    def draft(self, context):
        return self.message


class StubLLMClient:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls = response, error, []

    def chat(self, messages, temperature=0.2):
        self.calls.append(messages)
        if self.error:
            raise self.error
        return self.response


# --- ToneGuardValidator -------------------------------------------------------------------

def test_safe_message_passes(validator):
    result = validator.validate("Recordatorio de pago", SAFE_BODY, days_to_due=3)
    assert result.passed
    assert result.violations == []


@pytest.mark.parametrize("text", [
    "Usted está en la Banda Alta de nuestra cartera",
    "Su score interno ha bajado",
    "Por su riesgo alto le escribimos",
    "Su puntuación crediticia es baja",
    "Según nuestra calificación interna",
    "Tiene una probabilidad de mora elevada",
])
def test_internal_classification_is_rejected(validator, text):
    result = validator.validate("Aviso", text, days_to_due=-3)
    assert not result.passed
    assert ToneRule.INTERNAL_CLASSIFICATION in {v.rule for v in result.violations}


@pytest.mark.parametrize("text", [
    "Estimado cliente moroso",
    "MOROSA reincidente",
    "Iniciaremos una demanda en su contra",
    "Procederemos al embargo de sus bienes",
    "Podría terminar en la cárcel",
    "Reporte inmediato a centrales de riesgo",
    "Tomaremos acciones legales",
    "Usted es un deudor rebelde",
])
def test_stigmatizing_or_coercive_language_is_rejected(validator, text):
    result = validator.validate("Aviso", text, days_to_due=-3)
    assert not result.passed
    assert ToneRule.STIGMATIZING_OR_COERCIVE in {v.rule for v in result.violations}


@pytest.mark.parametrize("text", [
    "Pague URGENTE su cuota",
    "Este es su último aviso",
    "Regularice de inmediato",
    "Pague hoy mismo!!",
])
def test_urgency_rejected_before_due_date(validator, text):
    result = validator.validate("Aviso", text, days_to_due=2)
    assert not result.passed
    assert {v.rule for v in result.violations} == {ToneRule.PREVENTIVE_URGENCY}


def test_urgency_rule_not_applied_after_due_date(validator):
    result = validator.validate("Aviso", "Le pedimos regularizar de inmediato su cuota.", days_to_due=-2)
    assert result.passed


def test_due_date_itself_counts_as_preventive(validator):
    result = validator.validate("Aviso", "Pague urgente", days_to_due=0)
    assert not result.passed


@pytest.mark.parametrize("subject,body", [
    ("", SAFE_BODY),
    ("Aviso", "   "),
    ("Aviso", "Hola {{ customer_name }}"),
    ("Aviso", "Hola {% if x %}"),
])
def test_template_integrity(validator, subject, body):
    result = validator.validate(subject, body, days_to_due=3)
    assert not result.passed
    assert ToneRule.TEMPLATE_INTEGRITY in {v.rule for v in result.violations}


def test_word_boundaries_avoid_false_positives(validator):
    # "abandone" contiene "banda" pero no menciona una banda de riesgo.
    result = validator.validate("Aviso", "No queremos que abandone sus metas de ahorro.", days_to_due=3)
    assert result.passed


# --- DeterministicMessageDrafter ----------------------------------------------------------

@pytest.mark.parametrize("tone,days", [
    (Tone.NEUTRAL, 3), (Tone.NEUTRAL, -3), (Tone.PREVENTIVE, 5), (Tone.PREVENTIVE, 0), (Tone.FIRM, -4),
])
def test_all_templates_pass_tone_guard(validator, tone, days):
    draft = DeterministicMessageDrafter().draft(make_context(tone, days))
    assert not draft.used_llm
    assert NAME_PLACEHOLDER in draft.body_text
    assert format_money(150000.0) in draft.body_text
    assert due_phrase(days) in draft.body_text
    assert validator.validate(draft.subject, draft.body_text, days).passed


def test_deterministic_drafter_is_reproducible():
    drafter = DeterministicMessageDrafter()
    assert drafter.draft(make_context()) == drafter.draft(make_context())


def test_format_helpers():
    assert format_money(1234567.891) == "$1.234.567,89"
    assert due_phrase(1) == "vence mañana"
    assert due_phrase(0) == "vence hoy"
    assert due_phrase(-5) == "venció hace 5 días"


# --- compose_notice_message (pipeline + fallback) -----------------------------------------

def test_compose_personalizes_name_locally():
    message = compose_notice_message(make_context(), customer_name="Ana Pérez",
                                     drafter=DeterministicMessageDrafter())
    assert message.validation_status == VALIDATION_PASSED
    assert message.tone == Tone.PREVENTIVE
    assert "Ana Pérez" in message.body_text
    assert NAME_PLACEHOLDER not in message.body_text


def test_compose_falls_back_to_neutral_template_on_violation():
    bad = StubDrafter("Aviso de Banda Alta", "Estimado moroso, pague urgente o habrá embargo.")
    message = compose_notice_message(make_context(Tone.PREVENTIVE, 2), customer_name="Ana",
                                     drafter=bad)
    assert message.validation_status == VALIDATION_FALLBACK
    assert message.tone == Tone.NEUTRAL
    assert not message.used_llm
    assert {v.rule for v in message.violations} >= {
        ToneRule.INTERNAL_CLASSIFICATION, ToneRule.STIGMATIZING_OR_COERCIVE, ToneRule.PREVENTIVE_URGENCY,
    }
    neutral = DeterministicMessageDrafter().draft(make_context(Tone.NEUTRAL, 2))
    assert message.subject == neutral.subject
    assert "moroso" not in message.body_text.lower()


def test_compose_without_name_uses_generic_salutation():
    message = compose_notice_message(make_context(), drafter=DeterministicMessageDrafter())
    assert "Estimado(a) cliente:" in message.body_text


# --- LLMMessageDrafter --------------------------------------------------------------------

def test_llm_drafter_never_sends_pii_or_reference():
    client = StubLLMClient(response='{"subject": "Recordatorio", "body": "Estimado(a) [NOMBRE_CLIENTE]: su cuota vence pronto."}')
    draft = LLMMessageDrafter(client).draft(make_context())
    assert draft.used_llm
    sent = str(client.calls[0])
    assert "REF-001" not in sent
    message = compose_notice_message(make_context(), customer_name="Ana Pérez",
                                     drafter=LLMMessageDrafter(client))
    assert "Ana Pérez" in message.body_text
    assert "Ana Pérez" not in str(client.calls)


@pytest.mark.parametrize("client", [
    StubLLMClient(error=LLMUnavailableError("timeout")),
    StubLLMClient(response="no es json"),
    StubLLMClient(response='{"subject": 1}'),
])
def test_llm_drafter_falls_back_to_templates(client):
    draft = LLMMessageDrafter(client).draft(make_context())
    assert not draft.used_llm
    assert draft == DeterministicMessageDrafter().draft(make_context())


def test_llm_output_with_violation_is_replaced():
    client = StubLLMClient(response='```json\n{"subject": "Aviso", "body": "Su score indica que es moroso."}\n```')
    message = compose_notice_message(make_context(), drafter=LLMMessageDrafter(client))
    assert message.validation_status == VALIDATION_FALLBACK
    assert "score" not in message.body_text.lower()
