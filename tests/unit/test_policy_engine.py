"""
Pruebas unitarias del motor de políticas (T007, T008):
clasificación de bandas, histéresis y calidad de evidencia.

No dependen de SQLite ni del modelo de ML: usan la política real cargada
desde `config/politica.yaml` (fixture `policy_config`) y objetos sintéticos
simples para historial/pagos.
"""

from dataclasses import dataclass
from datetime import date
from typing import Optional

import pytest
from pydantic import ValidationError

from src.domain.entities import EvidenceQuality, RiskBand
from src.policy.config import (
    BandPolicyConfig,
    ContactWindowConfig,
    EvidenceRules,
    GeneralSettings,
    HysteresisRules,
    MultiArmedBanditConfig,
    PolicyConfig,
    load_policy_config,
)
from src.policy.engine import (
    apply_hysteresis,
    assess_evidence_quality,
    classify_risk_band,
    get_contact_window,
)


# ---------------------------------------------------------------------------
# Carga y validación de configuración (T010)
# ---------------------------------------------------------------------------


def test_load_policy_config_reads_real_yaml(policy_config: PolicyConfig):
    assert policy_config.version == "1.0.0"
    assert set(policy_config.bands.keys()) == set(RiskBand)
    assert policy_config.hysteresis_rules.probability_margin == pytest.approx(0.05)
    assert policy_config.hysteresis_rules.cycles_to_confirm == 2
    assert policy_config.evidence_rules.min_period_history == 3
    assert policy_config.evidence_rules.unreflected_payment_tolerance_days == 2


def test_load_policy_config_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        load_policy_config("config/no_existe.yaml")


def test_policy_config_rejects_non_ascending_thresholds():
    bands = {
        RiskBand.BAJA: _band(threshold=0.50),
        RiskBand.MODERADA: _band(threshold=0.40),  # inválido: debe ser > BAJA
        RiskBand.ALTA: _band(threshold=0.70),
        RiskBand.CRITICA: _band(threshold=1.00),
    }
    with pytest.raises(ValidationError):
        _make_policy(bands=bands)


def test_contact_window_disallowed_cannot_declare_notices():
    with pytest.raises(ValidationError):
        ContactWindowConfig(
            allowed=False,
            window_days_before_due=[1, 2],
            max_notices=0,
            min_separation_days=0,
            allowed_tones=["NEUTRAL"],
        )


def test_contact_window_allowed_requires_at_least_one_notice():
    with pytest.raises(ValidationError):
        ContactWindowConfig(
            allowed=True,
            window_days_before_due=[1, 2],
            max_notices=0,
            min_separation_days=0,
            allowed_tones=["NEUTRAL"],
        )


# ---------------------------------------------------------------------------
# Clasificación de banda (sin histéresis)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "probability,expected_band",
    [
        (0.0, RiskBand.BAJA),
        (0.15, RiskBand.BAJA),  # límite inclusivo
        (0.1501, RiskBand.MODERADA),
        (0.40, RiskBand.MODERADA),
        (0.4001, RiskBand.ALTA),
        (0.70, RiskBand.ALTA),
        (0.7001, RiskBand.CRITICA),
        (1.0, RiskBand.CRITICA),
    ],
)
def test_classify_risk_band_thresholds(policy_config: PolicyConfig, probability, expected_band):
    assert classify_risk_band(probability, policy_config) == expected_band


@pytest.mark.parametrize("probability", [-0.01, 1.01])
def test_classify_risk_band_rejects_out_of_range(policy_config: PolicyConfig, probability):
    with pytest.raises(ValueError):
        classify_risk_band(probability, policy_config)


# ---------------------------------------------------------------------------
# Histéresis
# ---------------------------------------------------------------------------


def test_hysteresis_initial_assignment_has_no_previous_band(policy_config: PolicyConfig):
    result = apply_hysteresis(0.20, previous_band=None, consecutive_cycles_in_candidate_band=0, policy=policy_config)
    assert result.confirmed_band == RiskBand.MODERADA
    assert result.band_change_confirmed is True
    assert result.rule_applied == "INITIAL_ASSIGNMENT"


def test_hysteresis_no_change_when_same_band(policy_config: PolicyConfig):
    result = apply_hysteresis(0.20, previous_band=RiskBand.MODERADA, consecutive_cycles_in_candidate_band=0, policy=policy_config)
    assert result.confirmed_band == RiskBand.MODERADA
    assert result.band_change_confirmed is False
    assert result.rule_applied == "NO_CHANGE"


def test_hysteresis_holds_when_candidate_within_margin_and_cycles_not_sustained(policy_config: PolicyConfig):
    # Frontera MODERADA/ALTA = 0.40; margen 0.05 => confirma a partir de 0.45.
    result = apply_hysteresis(0.42, previous_band=RiskBand.MODERADA, consecutive_cycles_in_candidate_band=0, policy=policy_config)
    assert result.candidate_band == RiskBand.ALTA
    assert result.confirmed_band == RiskBand.MODERADA
    assert result.band_change_confirmed is False
    assert result.rule_applied == "HYSTERESIS_HOLD"


def test_hysteresis_confirms_upgrade_when_margin_exceeded(policy_config: PolicyConfig):
    result = apply_hysteresis(0.45, previous_band=RiskBand.MODERADA, consecutive_cycles_in_candidate_band=0, policy=policy_config)
    assert result.confirmed_band == RiskBand.ALTA
    assert result.band_change_confirmed is True
    assert result.rule_applied == "MARGIN_EXCEEDED"


def test_hysteresis_confirms_upgrade_when_cycles_sustained_without_margin(policy_config: PolicyConfig):
    result = apply_hysteresis(0.41, previous_band=RiskBand.MODERADA, consecutive_cycles_in_candidate_band=2, policy=policy_config)
    assert result.confirmed_band == RiskBand.ALTA
    assert result.band_change_confirmed is True
    assert result.rule_applied == "CYCLES_SUSTAINED"


def test_hysteresis_confirms_downgrade_when_margin_exceeded(policy_config: PolicyConfig):
    # Frontera MODERADA/ALTA = 0.40; para confirmar baja desde ALTA se requiere <= 0.35.
    result = apply_hysteresis(0.30, previous_band=RiskBand.ALTA, consecutive_cycles_in_candidate_band=0, policy=policy_config)
    assert result.confirmed_band == RiskBand.MODERADA
    assert result.band_change_confirmed is True
    assert result.rule_applied == "MARGIN_EXCEEDED"


def test_hysteresis_holds_downgrade_within_margin(policy_config: PolicyConfig):
    result = apply_hysteresis(0.38, previous_band=RiskBand.ALTA, consecutive_cycles_in_candidate_band=1, policy=policy_config)
    assert result.candidate_band == RiskBand.MODERADA
    assert result.confirmed_band == RiskBand.ALTA
    assert result.band_change_confirmed is False
    assert result.rule_applied == "HYSTERESIS_HOLD"


# ---------------------------------------------------------------------------
# Calidad de evidencia
# ---------------------------------------------------------------------------


@dataclass
class _FakePeriodRecord:
    record_id: str


@dataclass
class _FakePendingPayment:
    payment_date: date
    status: str


def test_evidence_insufficient_when_too_few_periods(policy_config: PolicyConfig):
    history = [_FakePeriodRecord(record_id="r1"), _FakePeriodRecord(record_id="r2")]  # < min_period_history (3)
    result = assess_evidence_quality(history, [], cutoff_date=date(2026, 1, 10), evidence_rules=policy_config.evidence_rules)
    assert result == EvidenceQuality.INSUFFICIENT


def test_evidence_inconsistent_when_recent_unreflected_payment_in_process(policy_config: PolicyConfig):
    history = [_FakePeriodRecord(record_id=f"r{i}") for i in range(4)]
    cutoff = date(2026, 1, 10)
    pending = [_FakePendingPayment(payment_date=date(2026, 1, 9), status="IN_PROCESS")]  # 1 día, dentro de tolerancia (2)
    result = assess_evidence_quality(history, pending, cutoff_date=cutoff, evidence_rules=policy_config.evidence_rules)
    assert result == EvidenceQuality.INCONSISTENT


def test_evidence_sufficient_when_pending_payment_outside_tolerance(policy_config: PolicyConfig):
    history = [_FakePeriodRecord(record_id=f"r{i}") for i in range(4)]
    cutoff = date(2026, 1, 10)
    pending = [_FakePendingPayment(payment_date=date(2026, 1, 1), status="IN_PROCESS")]  # 9 días, fuera de tolerancia
    result = assess_evidence_quality(history, pending, cutoff_date=cutoff, evidence_rules=policy_config.evidence_rules)
    assert result == EvidenceQuality.SUFFICIENT


def test_evidence_sufficient_ignores_cleared_payments(policy_config: PolicyConfig):
    history = [_FakePeriodRecord(record_id=f"r{i}") for i in range(4)]
    cutoff = date(2026, 1, 10)
    pending = [_FakePendingPayment(payment_date=date(2026, 1, 9), status="CLEARED")]
    result = assess_evidence_quality(history, pending, cutoff_date=cutoff, evidence_rules=policy_config.evidence_rules)
    assert result == EvidenceQuality.SUFFICIENT


# ---------------------------------------------------------------------------
# Resolución de ventana de contacto
# ---------------------------------------------------------------------------


def test_get_contact_window_distinguishes_preventive_and_post_due(policy_config: PolicyConfig):
    preventive = get_contact_window(RiskBand.ALTA, is_preventive=True, policy=policy_config)
    post_due = get_contact_window(RiskBand.ALTA, is_preventive=False, policy=policy_config)
    assert preventive.window_days_before_due == [5, 4, 3, 2, 1]
    assert post_due.window_days_after_due == [1, 2, 3, 4, 5, 6, 7]


def test_get_contact_window_baja_preventive_is_disallowed(policy_config: PolicyConfig):
    preventive = get_contact_window(RiskBand.BAJA, is_preventive=True, policy=policy_config)
    assert preventive.allowed is False
    assert preventive.window_days_before_due == []


# ---------------------------------------------------------------------------
# Helpers de construcción de PolicyConfig sintética (para pruebas de validación)
# ---------------------------------------------------------------------------


def _band(threshold: float) -> BandPolicyConfig:
    return BandPolicyConfig(
        probability_threshold=threshold,
        preventive_contact=ContactWindowConfig(
            allowed=True,
            window_days_before_due=[1, 2],
            max_notices=1,
            min_separation_days=0,
            allowed_tones=["NEUTRAL"],
        ),
        post_due_contact=ContactWindowConfig(
            allowed=True,
            window_days_after_due=[1, 2],
            max_notices=1,
            min_separation_days=0,
            allowed_tones=["NEUTRAL"],
        ),
    )


def _make_policy(bands: Optional[dict] = None) -> PolicyConfig:
    return PolicyConfig(
        version="test",
        general_settings=GeneralSettings(
            timezone="America/Bogota",
            human_review_cutoff_time="09:00:00",
            dispatch_window_time="10:00:00",
            payment_clearing_delay_days=2,
            human_review_daily_capacity_ratio=0.2,
            avoided_management_cost_ref=1.0,
        ),
        hysteresis_rules=HysteresisRules(probability_margin=0.05, cycles_to_confirm=2),
        evidence_rules=EvidenceRules(min_period_history=3, unreflected_payment_tolerance_days=2),
        bands=bands
        or {
            RiskBand.BAJA: _band(0.15),
            RiskBand.MODERADA: _band(0.40),
            RiskBand.ALTA: _band(0.70),
            RiskBand.CRITICA: _band(1.00),
        },
        multi_armed_bandit=MultiArmedBanditConfig(exploration_rate=0.1, default_metric="on_time_payment_rate"),
    )
