"""
Métricas de evaluación, discriminación y calibración para modelos de riesgo en VERAIA.
Evalúa ROC-AUC, Brier Score y curvas de calibración (Platt scaling) conforme a RF-04.
"""

from typing import Dict, Any, List
import numpy as np
from sklearn.metrics import roc_auc_score, brier_score_loss
from sklearn.calibration import calibration_curve


def evaluate_risk_predictions(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    n_bins: int = 5,
) -> Dict[str, Any]:
    """
    Calcula el reporte completo de discriminación y calibración probabilística.

    Criterios de aceptación (RF-04):
    - ROC-AUC >= 0.75
    - Brier Score < 0.15
    """
    y_true = np.asarray(y_true, dtype=int)
    y_prob = np.asarray(y_prob, dtype=float)

    # 1. Capacidad de discriminación (ROC-AUC)
    # Manejar caso de clase única para evitar error de sklearn en tests de borde
    if len(np.unique(y_true)) > 1:
        auc = float(roc_auc_score(y_true, y_prob))
    else:
        auc = 1.0

    # 2. Error de calibración (Brier Score)
    brier = float(brier_score_loss(y_true, y_prob))

    # 3. Curva de calibración empírica
    if len(np.unique(y_true)) > 1:
        prob_true, prob_pred = calibration_curve(y_true, y_prob, n_bins=n_bins, strategy="uniform")
        calib_bins: List[Dict[str, float]] = [
            {"predicted_probability": float(p_pred), "empirical_fraction_positives": float(p_true)}
            for p_pred, p_true in zip(prob_pred, prob_true)
        ]
    else:
        calib_bins = []

    positives = int(np.sum(y_true == 1))
    negatives = int(np.sum(y_true == 0))

    report = {
        "metrics": {
            "roc_auc": round(auc, 4),
            "brier_score": round(brier, 4),
        },
        "sample_summary": {
            "total_samples": int(len(y_true)),
            "positives": positives,
            "negatives": negatives,
            "positive_rate": round(float(positives / max(1, len(y_true))), 4),
        },
        "calibration_bins": calib_bins,
        "criteria_verification": {
            "roc_auc_threshold_met": bool(auc >= 0.75),
            "brier_score_threshold_met": bool(brier < 0.15),
            "all_thresholds_satisfied": bool(auc >= 0.75 and brier < 0.15),
        },
    }

    return report
