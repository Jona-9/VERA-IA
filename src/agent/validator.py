"""
ToneGuardValidator: verificación ética y léxica de los avisos antes de su programación (RF-10).

Reglas (contracts/agent_protocols.md §2 y Constitución VIII):
1. INTERNAL_CLASSIFICATION: prohibido mencionar bandas, scores o calificaciones internas.
2. STIGMATIZING_OR_COERCIVE: prohibido lenguaje estigmatizante, amenazante o coercitivo.
3. PREVENTIVE_URGENCY: antes del vencimiento (days_to_due >= 0) no se admiten apremios.
4. TEMPLATE_INTEGRITY: el mensaje no puede estar vacío ni contener marcadores sin renderizar.

La comparación se hace sobre texto normalizado (minúsculas y sin tildes) para que variantes
como "MOROSO" o "cárcel"/"carcel" no evadan el filtro.
"""

import re
import unicodedata
from enum import Enum
from typing import List, Tuple

from pydantic import BaseModel, Field


class ToneRule(str, Enum):
    INTERNAL_CLASSIFICATION = "INTERNAL_CLASSIFICATION"
    STIGMATIZING_OR_COERCIVE = "STIGMATIZING_OR_COERCIVE"
    PREVENTIVE_URGENCY = "PREVENTIVE_URGENCY"
    TEMPLATE_INTEGRITY = "TEMPLATE_INTEGRITY"


# Patrones expresados sobre texto normalizado (sin tildes, minúsculas).
INTERNAL_CLASSIFICATION_PATTERNS: Tuple[str, ...] = (
    r"\bbandas?\b",
    r"\briesgo\s+(alto|bajo|moderado|critico)\b",
    r"\b(alto|bajo|moderado|critico)\s+riesgo\b",
    r"\bscor(e|es|ing)\b",
    r"\bpuntuacion(es)?\s+crediticia",
    r"\bpuntaje\b",
    r"\bcalificacion(es)?\s+interna",
    r"\bclasificacion(es)?\s+interna",
    r"\bprobabilidad\s+de\s+(mora|atraso|impago|incumplimiento)\b",
)

STIGMATIZING_OR_COERCIVE_PATTERNS: Tuple[str, ...] = (
    r"\bmoros[oa]s?\b",
    r"\bmorosidad\b",
    r"\bdeudor(es)?\s+rebelde",
    r"\bdemanda(s|r|remos|ra)?\b",
    r"\bembarg(o|os|ar|aremos|ara)\b",
    r"\bcarcel\b",
    r"\bprision\b",
    r"\breporte\s+inmediato\s+a\s+centrales\b",
    r"\bcentrales\s+de\s+riesgo\b",
    r"\bacciones?\s+(legales|judiciales)\b",
    r"\bconsecuencias\s+(legales|judiciales)\b",
    r"\bproceso\s+judicial\b",
    r"\bjuicio\b",
    r"\babogad[oa]s?\b",
    r"\bamenaza",
    r"\bincumplid[oa]\b",
    r"\birresponsable",
)

PREVENTIVE_URGENCY_PATTERNS: Tuple[str, ...] = (
    r"\burgente(mente)?\b",
    r"\bde\s+inmediato\b",
    r"\binmediatamente\b",
    r"\bultimo\s+aviso\b",
    r"\bultima\s+oportunidad\b",
    r"\bhoy\s+mismo\b",
    r"\bsin\s+falta\b",
    r"\bplazo\s+final\b",
    r"\bobligatoriamente\b",
    r"!{2,}",
)

TEMPLATE_RESIDUE_PATTERN = re.compile(r"\{\{|\}\}|\{%|%\}")


class ToneViolation(BaseModel):
    rule: ToneRule
    matched_text: str = Field(description="Fragmento normalizado que activó la regla")


class ToneValidationResult(BaseModel):
    passed: bool
    violations: List[ToneViolation] = Field(default_factory=list)

    @property
    def summary(self) -> str:
        return "; ".join(f"{v.rule.value}: '{v.matched_text}'" for v in self.violations)


def normalize_text(text: str) -> str:
    """Pasa a minúsculas y elimina tildes/diacríticos."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _compile(patterns: Tuple[str, ...]) -> List[re.Pattern]:
    return [re.compile(p) for p in patterns]


class ToneGuardValidator:
    """Valida asunto y cuerpo de un aviso contra las reglas de buen trato."""

    def __init__(self):
        self._internal = _compile(INTERNAL_CLASSIFICATION_PATTERNS)
        self._coercive = _compile(STIGMATIZING_OR_COERCIVE_PATTERNS)
        self._urgency = _compile(PREVENTIVE_URGENCY_PATTERNS)

    def validate(self, subject: str, body_text: str, days_to_due: int) -> ToneValidationResult:
        violations: List[ToneViolation] = []

        if not subject.strip() or not body_text.strip():
            violations.append(ToneViolation(rule=ToneRule.TEMPLATE_INTEGRITY, matched_text="<vacío>"))
        residue = TEMPLATE_RESIDUE_PATTERN.search(subject + "\n" + body_text)
        if residue:
            violations.append(
                ToneViolation(rule=ToneRule.TEMPLATE_INTEGRITY, matched_text=residue.group(0))
            )

        normalized = normalize_text(subject + "\n" + body_text)
        violations += self._scan(normalized, self._internal, ToneRule.INTERNAL_CLASSIFICATION)
        violations += self._scan(normalized, self._coercive, ToneRule.STIGMATIZING_OR_COERCIVE)
        if days_to_due >= 0:
            violations += self._scan(normalized, self._urgency, ToneRule.PREVENTIVE_URGENCY)

        return ToneValidationResult(passed=not violations, violations=violations)

    @staticmethod
    def _scan(text: str, patterns: List[re.Pattern], rule: ToneRule) -> List[ToneViolation]:
        found = []
        for pattern in patterns:
            match = pattern.search(text)
            if match:
                found.append(ToneViolation(rule=rule, matched_text=match.group(0)))
        return found
