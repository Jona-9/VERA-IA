"""
Pruebas unitarias para el modelo predictivo de riesgo y calibración.
Verifica:
- Cumplimiento de criterios: ROC-AUC >= 0.75 y Brier Score < 0.15
- Calibración de probabilidades en [0, 1]
- Reproducibilidad determinista (random_state=42)
- Explicabilidad de coeficientes
- Serialización y carga de artefactos
"""

import os
import tempfile
import pytest
import numpy as np

from src.analytics.model import RiskModel
from src.analytics.metrics import evaluate_risk_predictions
from src.analytics.signals import compute_signals_for_account


def test_model_training_and_thresholds(synthetic_training_data):
    """Verifica que el modelo calibrado cumple los umbrales de ROC-AUC y Brier Score."""
    X, y = synthetic_training_data

    # Split 80/20 simple para evaluación
    train_size = int(len(X) * 0.8)
    X_train, X_test = X.iloc[:train_size], X.iloc[train_size:]
    y_train, y_test = y.iloc[:train_size], y.iloc[train_size:]

    model = RiskModel(random_state=42, cv=3)
    model.fit(X_train, y_train)

    probs = model.predict_calibrated_proba(X_test)

    # Validar acotamiento estricto
    assert np.all(probs >= 0.0)
    assert np.all(probs <= 1.0)

    report = evaluate_risk_predictions(y_test, probs)

    auc = report["metrics"]["roc_auc"]
    brier = report["metrics"]["brier_score"]

    assert auc >= 0.75, f"ROC-AUC insuficiente: {auc} < 0.75"
    assert brier < 0.15, f"Brier Score muy alto: {brier} >= 0.15"
    assert report["criteria_verification"]["all_thresholds_satisfied"] is True


def test_model_determinism_and_reproducibility(synthetic_training_data):
    """Verifica que con la misma semilla se obtienen exactamente las mismas predicciones y coeficientes."""
    X, y = synthetic_training_data

    model1 = RiskModel(random_state=42, cv=3).fit(X, y)
    model2 = RiskModel(random_state=42, cv=3).fit(X, y)

    probs1 = model1.predict_calibrated_proba(X)
    probs2 = model2.predict_calibrated_proba(X)

    np.testing.assert_allclose(probs1, probs2, rtol=1e-5)
    assert model1.get_coefficients() == model2.get_coefficients()
    assert model1.get_intercept() == model2.get_intercept()


def test_monotonic_risk_behavior(
    synthetic_training_data,
    punctual_account_and_history,
    deteriorating_account_and_history,
    cutoff_date,
):
    """
    Verifica comportamiento monótono de riesgo:
    Un cliente en deterioro evidente debe recibir una probabilidad calibrada
    sustancialmente mayor que un cliente puntual.
    """
    X, y = synthetic_training_data
    model = RiskModel(random_state=42, cv=3).fit(X, y)

    acc_punc, recs_punc = punctual_account_and_history
    signals_punc = compute_signals_for_account(acc_punc, recs_punc, cutoff_date)

    acc_det, recs_det = deteriorating_account_and_history
    signals_det = compute_signals_for_account(acc_det, recs_det, cutoff_date)

    raw_punc, calib_punc = model.evaluate_signals(signals_punc)
    raw_det, calib_det = model.evaluate_signals(signals_det)

    assert calib_det > calib_punc, (
        f"Inconsistencia: cliente en deterioro ({calib_det}) no supera al puntual ({calib_punc})"
    )
    assert calib_punc < 0.35
    assert calib_det > 0.50


def test_model_serialization_joblib(synthetic_training_data):
    """Verifica guardado y recarga determinista del artefacto del modelo."""
    X, y = synthetic_training_data
    model = RiskModel(random_state=42, cv=3).fit(X, y)
    probs_orig = model.predict_calibrated_proba(X)

    with tempfile.TemporaryDirectory() as tmpdir:
        model_path = os.path.join(tmpdir, "test_risk_model.joblib")
        model.save(model_path)
        assert os.path.exists(model_path)

        loaded_model = RiskModel.load(model_path)
        probs_loaded = loaded_model.predict_calibrated_proba(X)

        np.testing.assert_allclose(probs_orig, probs_loaded)
        assert loaded_model.get_coefficients() == model.get_coefficients()


def test_feature_coefficients_explicability(synthetic_training_data):
    """Verifica que todos los coeficientes estén presentes para auditoría y trazabilidad."""
    X, y = synthetic_training_data
    model = RiskModel(random_state=42, cv=3).fit(X, y)

    coeffs = model.get_coefficients()
    assert len(coeffs) == 7
    assert "credit_utilization_ratio" in coeffs
    assert "consecutive_min_payments" in coeffs
    assert "payment_ratio_drop" in coeffs
    assert isinstance(model.get_intercept(), float)
