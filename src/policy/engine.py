"""
Motor de políticas: clasificación en bandas de riesgo con histéresis (RF-05) y
tipificación de calidad de evidencia (RF-06).

Este módulo es puro (sin I/O, sin estado mutable compartido): recibe la
configuración ya validada (`PolicyConfig`) y los datos observados de la cuenta,
y devuelve veredictos auditable explicados mediante `rule_applied` /
`explanation`-friendly resultados. Así cualquier integrante puede probarlo con
diccionarios y objetos mock sin depender de SQLite ni del modelo de ML.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import List, Optional, Protocol

from src.domain.entities import EvidenceQuality, RiskBand
from src.policy.config import ContactWindowConfig, EvidenceRules, PolicyConfig

# ---------------------------------------------------------------------------
# Clasificación de banda (sin histéresis)
# ---------------------------------------------------------------------------


def classify_risk_band(probability: float, policy: PolicyConfig) -> RiskBand:
    """
    Clasifica una probabilidad calibrada en la banda de riesgo correspondiente.

    Los `probability_threshold` de `config/politica.yaml` son límites
    superiores inclusivos: BAJA <= 0.15 < MODERADA <= 0.40 < ALTA <= 0.70 <
    CRITICA <= 1.00. Esta función es la clasificación "cruda"; la decisión
    final de banda la determina `apply_hysteresis`.
    """
    if not 0.0 <= probability <= 1.0:
        raise ValueError(f"La probabilidad debe estar en [0, 1], recibido: {probability}")

    for band in policy.band_order():
        if probability <= policy.bands[band].probability_threshold:
            return band
    # Inalcanzable si PolicyConfig valida que la banda CRITICA cubre 1.0.
    raise ValueError("Ninguna banda cubre la probabilidad dada; revisar config/politica.yaml")


# ---------------------------------------------------------------------------
# Histéresis
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HysteresisResult:
    """Veredicto auditable de la evaluación de histéresis."""

    confirmed_band: RiskBand
    candidate_band: RiskBand
    band_change_confirmed: bool
    rule_applied: str
    explanation: str


def _band_boundary_threshold(band_a: RiskBand, band_b: RiskBand, policy: PolicyConfig) -> float:
    """
    Umbral de probabilidad que separa `band_a` y `band_b` (bandas adyacentes
    o no). Es el `probability_threshold` de la banda con menor severidad entre
    ambas, ya que ese valor es exactamente la frontera que hay que cruzar para
    pasar de una a la otra.
    """
    order = policy.band_order()
    lower_band = band_a if order.index(band_a) < order.index(band_b) else band_b
    return policy.bands[lower_band].probability_threshold


def apply_hysteresis(
    probability: float,
    previous_band: Optional[RiskBand],
    consecutive_cycles_in_candidate_band: int,
    policy: PolicyConfig,
) -> HysteresisResult:
    """
    Decide si un cambio de banda candidato se confirma o se mantiene en la
    banda anterior, aplicando la regla constitucional: el cambio exige
    superar el umbral de frontera por `probability_margin` (0.05), O
    sostenerse `cycles_to_confirm` (2) ciclos consecutivos en la banda
    candidata aunque esté dentro del margen de tolerancia.

    `consecutive_cycles_in_candidate_band` es responsabilidad del llamador
    (persistencia/orquestador): cuenta cuántos ciclos *consecutivos* la
    clasificación cruda (`classify_risk_band`) ha arrojado la misma banda
    candidata distinta de `previous_band`, incluyendo el ciclo actual. Este
    motor no guarda estado entre llamadas para permanecer puro y testeable.

    Nota de diseño: se interpreta "superar el umbral por 0.05" como superar
    por ese margen el umbral de *frontera* entre la banda anterior y la banda
    candidata (no la probabilidad del ciclo anterior), de forma que el margen
    sea independiente de cuánto fluctuó el score y solo dependa de qué tan
    lejos del límite de banda cae la nueva observación.
    """
    candidate_band = classify_risk_band(probability, policy)

    if previous_band is None:
        return HysteresisResult(
            confirmed_band=candidate_band,
            candidate_band=candidate_band,
            band_change_confirmed=True,
            rule_applied="INITIAL_ASSIGNMENT",
            explanation=f"Primera evaluación de la cuenta: se asigna directamente la banda {candidate_band.value}.",
        )

    if candidate_band == previous_band:
        return HysteresisResult(
            confirmed_band=previous_band,
            candidate_band=candidate_band,
            band_change_confirmed=False,
            rule_applied="NO_CHANGE",
            explanation=f"La banda candidata coincide con la banda previa ({previous_band.value}); no hay cambio.",
        )

    order = policy.band_order()
    is_upgrade = order.index(candidate_band) > order.index(previous_band)
    boundary = _band_boundary_threshold(previous_band, candidate_band, policy)
    margin = policy.hysteresis_rules.probability_margin

    if is_upgrade:
        margin_exceeded = probability >= boundary + margin
    else:
        margin_exceeded = probability <= boundary - margin

    if margin_exceeded:
        return HysteresisResult(
            confirmed_band=candidate_band,
            candidate_band=candidate_band,
            band_change_confirmed=True,
            rule_applied="MARGIN_EXCEEDED",
            explanation=(
                f"La probabilidad {probability:.4f} supera el margen de {margin:.2f} sobre la frontera "
                f"{boundary:.2f} entre {previous_band.value} y {candidate_band.value}; cambio confirmado."
            ),
        )

    if consecutive_cycles_in_candidate_band >= policy.hysteresis_rules.cycles_to_confirm:
        return HysteresisResult(
            confirmed_band=candidate_band,
            candidate_band=candidate_band,
            band_change_confirmed=True,
            rule_applied="CYCLES_SUSTAINED",
            explanation=(
                f"La banda candidata {candidate_band.value} se sostuvo "
                f"{consecutive_cycles_in_candidate_band} ciclos consecutivos "
                f"(>= {policy.hysteresis_rules.cycles_to_confirm}); cambio confirmado sin superar el margen."
            ),
        )

    return HysteresisResult(
        confirmed_band=previous_band,
        candidate_band=candidate_band,
        band_change_confirmed=False,
        rule_applied="HYSTERESIS_HOLD",
        explanation=(
            f"La banda candidata {candidate_band.value} no superó el margen de {margin:.2f} sobre la frontera "
            f"{boundary:.2f} ni se sostuvo {policy.hysteresis_rules.cycles_to_confirm} ciclos "
            f"(lleva {consecutive_cycles_in_candidate_band}); se mantiene la banda previa {previous_band.value}."
        ),
    )


# ---------------------------------------------------------------------------
# Calidad de evidencia
# ---------------------------------------------------------------------------


class _PeriodRecordLike(Protocol):
    """Forma mínima requerida de un registro histórico (duck typing con PeriodRecord/PeriodRecordDTO)."""

    @property
    def record_id(self) -> str: ...


class _PendingPaymentLike(Protocol):
    """Forma mínima requerida de un pago en trámite (duck typing con PendingPayment/PendingPaymentDTO)."""

    @property
    def payment_date(self) -> date: ...

    @property
    def status(self) -> str: ...


def assess_evidence_quality(
    period_history: List[_PeriodRecordLike],
    pending_payments: List[_PendingPaymentLike],
    cutoff_date: date,
    evidence_rules: EvidenceRules,
) -> EvidenceQuality:
    """
    Tipifica la calidad de la evidencia disponible para una cuenta a
    `cutoff_date` (RF-06):

    - `INSUFFICIENT`: hay menos períodos históricos que
      `evidence_rules.min_period_history`; no hay base suficiente para
      confiar en las señales calculadas.
    - `INCONSISTENT`: existe un pago en trámite (`IN_PROCESS`) emitido dentro
      de la ventana de tolerancia (`unreflected_payment_tolerance_days`)
      respecto a `cutoff_date`, es decir, el cliente pudo haber pagado pero el
      abono aún no se refleja en el historial usado para las señales.
    - `SUFFICIENT`: en cualquier otro caso.

    El orden de evaluación prioriza `INSUFFICIENT` sobre `INCONSISTENT`: sin
    historial mínimo no hay forma confiable de contrastar montos, así que esa
    condición domina.
    """
    if len(period_history) < evidence_rules.min_period_history:
        return EvidenceQuality.INSUFFICIENT

    for payment in pending_payments:
        if payment.status != "IN_PROCESS":
            continue
        days_since_payment = (cutoff_date - payment.payment_date).days
        if 0 <= days_since_payment <= evidence_rules.unreflected_payment_tolerance_days:
            return EvidenceQuality.INCONSISTENT

    return EvidenceQuality.SUFFICIENT


# ---------------------------------------------------------------------------
# Resolución de la ventana de contacto vigente (uso compartido con las herramientas)
# ---------------------------------------------------------------------------


def get_contact_window(risk_band: RiskBand, is_preventive: bool, policy: PolicyConfig) -> ContactWindowConfig:
    """Devuelve la configuración de ventana (preventiva o post-vencimiento) para una banda."""
    band_policy = policy.bands[risk_band]
    return band_policy.preventive_contact if is_preventive else band_policy.post_due_contact
