"""
Pruebas unitarias para la extracción y cálculo de señales a fecha de corte.
Verifica cumplimiento estricto de:
- Aislamiento temporal / no-lookahead (Principio de cero fuga de información)
- Detección precisa de deterioro temprano (utilización, pagos mínimos consecutivos, caída de ratio)
- Manejo de cuentas con historial corto
"""

from datetime import date
import pytest

from src.domain.entities import SignalSet
from src.analytics.signals import compute_signals_for_account


def test_temporal_isolation_no_lookahead(future_leakage_history, cutoff_date):
    """
    CRÍTICO: Ningún dato con billing_date o registro posterior a cutoff_date
    debe influir en el cálculo de señales.
    """
    account, records = future_leakage_history

    # A fecha de corte 2026-10-15:
    # Existen 2 registros pasados (días mora = 0) y 1 futuro a 2026-10-28 (días mora = 45).
    signals = compute_signals_for_account(
        account=account,
        history=records,
        cutoff_date=cutoff_date,
    )

    assert isinstance(signals, SignalSet)
    assert signals.account_id == account.account_id
    assert signals.cutoff_date == cutoff_date

    # Debe ignorar completamente el registro futuro con 45 días de mora
    assert signals.max_past_due_days == 0, (
        f"Data leakage detectado: max_past_due_days={signals.max_past_due_days}, se esperaba 0"
    )
    assert signals.historical_delinquency_rate == 0.0


def test_deteriorating_signals_detection(deteriorating_account_and_history, cutoff_date):
    """
    Verifica detección de señales tempranas de deterioro antes del atraso:
    - Uso de línea alto (~95%)
    - Conteo de pagos mínimos consecutivos >= 3
    - Caída porcentual en monto pagado
    """
    account, records = deteriorating_account_and_history

    signals = compute_signals_for_account(
        account=account,
        history=records,
        cutoff_date=cutoff_date,
    )

    # Utilización de la línea a fecha de corte: 9500 / 10000 = 0.95
    assert pytest.approx(signals.credit_utilization_ratio, rel=1e-2) == 0.95

    # Al menos 3 meses consecutivos pagando únicamente el mínimo
    assert signals.consecutive_min_payments >= 3

    # El monto pagado en los últimos meses cayó significativamente respecto al histórico
    assert signals.payment_ratio_drop > 0.0

    # Aún no incurre en mora (señal temprana de advertencia)
    assert signals.max_past_due_days == 0
    assert signals.historical_delinquency_rate == 0.0


def test_punctual_signals_detection(punctual_account_and_history, cutoff_date):
    """Verifica señales de cliente puntual y de bajo riesgo."""
    account, records = punctual_account_and_history

    signals = compute_signals_for_account(
        account=account,
        history=records,
        cutoff_date=cutoff_date,
    )

    assert pytest.approx(signals.credit_utilization_ratio, rel=1e-2) == 0.15
    assert signals.consecutive_min_payments == 0
    assert signals.historical_delinquency_rate == 0.0
    assert signals.max_past_due_days == 0
    assert pytest.approx(signals.payment_to_billed_ratio, rel=1e-2) == 1.0


def test_chronic_delinquent_signals(chronic_delinquent_account_and_history, cutoff_date):
    """Verifica métricas de mora recurrente y tendencia creciente."""
    account, records = chronic_delinquent_account_and_history

    signals = compute_signals_for_account(
        account=account,
        history=records,
        cutoff_date=cutoff_date,
    )

    assert signals.historical_delinquency_rate >= 0.8
    assert signals.max_past_due_days >= 30
    assert signals.delinquency_trend > 0.0


def test_short_history_safe_calculation(short_history_account_and_history, cutoff_date):
    """Verifica que un historial < 3 períodos no falle con división por cero."""
    account, records = short_history_account_and_history

    signals = compute_signals_for_account(
        account=account,
        history=records,
        cutoff_date=cutoff_date,
    )

    assert isinstance(signals, SignalSet)
    assert signals.credit_utilization_ratio >= 0.0
    assert signals.consecutive_min_payments >= 0
    assert signals.payment_ratio_drop >= 0.0
    assert signals.historical_delinquency_rate >= 0.0
