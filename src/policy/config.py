"""
Cargador y validador de la política declarativa de contacto (config/politica.yaml).

Implementa RF-08: toda regla de negocio relativa a ventanas de contacto, cuotas,
separación mínima, tonos permitidos, histéresis y calidad de evidencia vive
declarada en YAML y se tipa estrictamente con Pydantic antes de ser consumida
por el motor de políticas (`src/policy/engine.py`) y por las herramientas de
acción (`src/tools/schedule_tool.py`).

No se inventan valores por defecto silenciosos: si el YAML no cumple el
esquema, la carga falla de forma explícita (fail-fast) en vez de dejar que una
regla de buen trato quede mal configurada en tiempo de ejecución.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

from src.domain.entities import RiskBand, Tone

DEFAULT_POLICY_PATH = "config/politica.yaml"


class GeneralSettings(BaseModel):
    """Parámetros operativos globales del ciclo diario de cobranza."""

    timezone: str
    human_review_cutoff_time: str
    dispatch_window_time: str
    payment_clearing_delay_days: int = Field(ge=0)
    human_review_daily_capacity_ratio: float = Field(ge=0, le=1)
    avoided_management_cost_ref: float = Field(ge=0)


class HysteresisRules(BaseModel):
    """Reglas de histéresis para confirmar un cambio de banda de riesgo."""

    probability_margin: float = Field(
        ge=0, le=1, description="Margen que debe superar la probabilidad sobre el umbral de frontera"
    )
    cycles_to_confirm: int = Field(
        ge=1, description="Ciclos consecutivos sosteniendo la banda candidata que confirman el cambio sin margen"
    )


class EvidenceRules(BaseModel):
    """Reglas para tipificar la calidad de la evidencia observada."""

    min_period_history: int = Field(ge=0, description="Mínimo de períodos históricos para considerar evidencia confiable")
    unreflected_payment_tolerance_days: int = Field(
        ge=0, description="Ventana en días para considerar un pago reciente como aún no reflejado"
    )


class ContactWindowConfig(BaseModel):
    """Configuración de una fase de contacto (preventiva o post-vencimiento) para una banda."""

    allowed: bool
    window_days_before_due: List[int] = Field(default_factory=list)
    window_days_after_due: List[int] = Field(default_factory=list)
    max_notices: int = Field(ge=0)
    min_separation_days: int = Field(ge=0)
    allowed_tones: List[Tone]

    @field_validator("window_days_before_due", "window_days_after_due")
    @classmethod
    def _non_negative_days(cls, value: List[int]) -> List[int]:
        if any(day <= 0 for day in value):
            raise ValueError("Los días de ventana deben ser enteros positivos (distancia a due_date)")
        return value

    @model_validator(mode="after")
    def _consistent_with_allowed_flag(self) -> "ContactWindowConfig":
        has_window = bool(self.window_days_before_due or self.window_days_after_due)
        if not self.allowed and (has_window or self.max_notices > 0):
            raise ValueError(
                "Una fase de contacto marcada como 'allowed: false' no puede declarar ventanas ni cupo de avisos"
            )
        if self.allowed and self.max_notices == 0:
            raise ValueError("Una fase de contacto permitida debe declarar max_notices >= 1")
        return self


class BandPolicyConfig(BaseModel):
    """Política completa asociada a una banda de riesgo."""

    probability_threshold: float = Field(ge=0, le=1)
    preventive_contact: ContactWindowConfig
    post_due_contact: ContactWindowConfig


class MultiArmedBanditConfig(BaseModel):
    """Parámetros de la simulación de asignación epsilon-greedy (uso de Dev 5)."""

    exploration_rate: float = Field(ge=0, le=1)
    default_metric: str


class PolicyConfig(BaseModel):
    """Raíz tipada de `config/politica.yaml`."""

    version: str
    general_settings: GeneralSettings
    hysteresis_rules: HysteresisRules
    evidence_rules: EvidenceRules
    bands: Dict[RiskBand, BandPolicyConfig]
    multi_armed_bandit: MultiArmedBanditConfig

    @model_validator(mode="after")
    def _all_bands_present_and_ordered(self) -> "PolicyConfig":
        missing = set(RiskBand) - set(self.bands.keys())
        if missing:
            raise ValueError(f"Faltan bandas de riesgo obligatorias en la política: {sorted(missing)}")

        ordered_bands = [RiskBand.BAJA, RiskBand.MODERADA, RiskBand.ALTA, RiskBand.CRITICA]
        thresholds = [self.bands[band].probability_threshold for band in ordered_bands]
        if thresholds != sorted(thresholds):
            raise ValueError(
                "Los umbrales de probabilidad por banda deben ser estrictamente crecientes: "
                f"BAJA < MODERADA < ALTA < CRITICA (recibido {thresholds})"
            )
        if thresholds[-1] != 1.0:
            raise ValueError("El umbral de la banda CRITICA debe ser 1.0 (cubre el resto del rango de probabilidad)")
        return self

    def band_order(self) -> List[RiskBand]:
        """Orden ascendente de severidad usado por el motor de histéresis."""
        return [RiskBand.BAJA, RiskBand.MODERADA, RiskBand.ALTA, RiskBand.CRITICA]


def load_policy_config(path: str | Path = DEFAULT_POLICY_PATH) -> PolicyConfig:
    """
    Carga y valida `config/politica.yaml` (o la ruta indicada) contra `PolicyConfig`.

    Lanza `FileNotFoundError` si el archivo no existe y `pydantic.ValidationError`
    si el contenido no respeta el esquema declarado en
    `sdd/specs/001-early-collection-agent/contracts/policy_schema.yaml`.
    """
    file_path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(f"No se encontró el archivo de política en: {file_path}")

    with file_path.open("r", encoding="utf-8") as handle:
        raw_data = yaml.safe_load(handle)

    if not isinstance(raw_data, dict):
        raise ValueError(f"El archivo de política {file_path} está vacío o no es un mapeo YAML válido")

    return PolicyConfig.model_validate(raw_data)
