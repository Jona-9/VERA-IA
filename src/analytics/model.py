"""
Modelo de predicción de riesgo y estimación calibrada para VERAIA.
Implementa Regresión Logística con Platt Scaling (CalibratedClassifierCV) conforme a RF-04.
"""

from typing import Dict, Any, Optional, List, Tuple
import os
import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.calibration import CalibratedClassifierCV

from src.analytics.signals import FEATURE_COLUMNS, SignalSet, signal_set_to_features


class RiskModel:
    """
    Modelo probabilístico de atraso temprano.
    Combina Regresión Logística estandarizada con CalibratedClassifierCV (sigmoid / Platt scaling).
    """

    def __init__(self, random_state: int = 42, cv: int = 3):
        self.random_state = random_state
        self.cv = cv
        self.feature_names = list(FEATURE_COLUMNS)

        # Pipeline base auditable y explicable
        self.base_pipeline = Pipeline(
            [
                ("scaler", StandardScaler()),
                (
                    "classifier",
                    LogisticRegression(
                        solver="lbfgs",
                        random_state=self.random_state,
                        max_iter=1000,
                    ),
                ),
            ]
        )

        # Envoltura de calibración por Platt scaling
        self.calibrated_model = CalibratedClassifierCV(
            estimator=self.base_pipeline,
            method="sigmoid",
            cv=self.cv,
        )
        self.is_fitted = False

    def _prepare_features(self, X: Any) -> pd.DataFrame:
        """Asegura formato tabular consistente con los nombres de características."""
        if isinstance(X, SignalSet):
            X = pd.DataFrame([signal_set_to_features(X)])
        elif isinstance(X, dict):
            X = pd.DataFrame([X])
        elif isinstance(X, list) and len(X) > 0 and isinstance(X[0], SignalSet):
            X = pd.DataFrame([signal_set_to_features(s) for s in X])
        elif isinstance(X, np.ndarray):
            X = pd.DataFrame(X, columns=self.feature_names[: X.shape[1]])
        elif isinstance(X, pd.DataFrame):
            # Filtrar columnas si hay más presentes
            missing = [col for col in self.feature_names if col not in X.columns]
            if missing:
                raise ValueError(f"Faltan características requeridas en los datos: {missing}")
            X = X[self.feature_names]
        else:
            raise TypeError(f"Tipo de entrada no soportado: {type(X)}")

        return X

    def fit(self, X: Any, y: Any) -> "RiskModel":
        """Entrena el modelo base y el calibrador sigmoid."""
        X_df = self._prepare_features(X)
        y_arr = np.asarray(y, dtype=int)

        # Ajuste del pipeline base para explicabilidad directa
        self.base_pipeline.fit(X_df, y_arr)

        # Ajuste del modelo calibrado
        self.calibrated_model.fit(X_df, y_arr)
        self.is_fitted = True
        return self

    def predict_raw_proba(self, X: Any) -> np.ndarray:
        """Retorna la probabilidad cruda de atraso (Regresión Logística directa)."""
        if not self.is_fitted:
            raise RuntimeError("El modelo debe ser entrenado antes de predecir.")
        X_df = self._prepare_features(X)
        return self.base_pipeline.predict_proba(X_df)[:, 1]

    def predict_calibrated_proba(self, X: Any) -> np.ndarray:
        """Retorna la probabilidad calibrada mediante Platt scaling (sigmoid)."""
        if not self.is_fitted:
            raise RuntimeError("El modelo debe ser entrenado antes de predecir.")
        X_df = self._prepare_features(X)
        return self.calibrated_model.predict_proba(X_df)[:, 1]

    def predict_proba(self, X: Any) -> np.ndarray:
        """Por defecto, retorna la probabilidad calibrada."""
        return self.predict_calibrated_proba(X)

    def predict(self, X: Any, threshold: float = 0.5) -> np.ndarray:
        """Predice clase binaria (0 = sin atraso, 1 = con atraso) usando un umbral."""
        probs = self.predict_calibrated_proba(X)
        return (probs >= threshold).astype(int)

    def evaluate_signals(self, signals: SignalSet) -> Tuple[float, float]:
        """
        Evalúa un objeto SignalSet individual y retorna:
        (raw_probability, calibrated_probability)
        """
        raw_p = float(self.predict_raw_proba(signals)[0])
        calib_p = float(self.predict_calibrated_proba(signals)[0])
        # Asegurar acotamiento estricto
        raw_p = max(0.0, min(1.0, raw_p))
        calib_p = max(0.0, min(1.0, calib_p))
        return raw_p, calib_p

    def get_coefficients(self) -> Dict[str, float]:
        """Retorna los coeficientes de las variables para explicabilidad y auditoría."""
        if not self.is_fitted:
            raise RuntimeError("El modelo debe ser entrenado antes de consultar coeficientes.")
        clf = self.base_pipeline.named_steps["classifier"]
        coeffs = clf.coef_[0]
        return {feat: round(float(coef), 4) for feat, coef in zip(self.feature_names, coeffs)}

    def get_intercept(self) -> float:
        """Retorna el intercepto del modelo base."""
        if not self.is_fitted:
            raise RuntimeError("El modelo debe ser entrenado antes de consultar el intercepto.")
        clf = self.base_pipeline.named_steps["classifier"]
        return round(float(clf.intercept_[0]), 4)

    def save(self, filepath: str) -> None:
        """Serializa el modelo a disco con joblib."""
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        joblib.dump(self, filepath)

    @classmethod
    def load(cls, filepath: str) -> "RiskModel":
        """Carga un modelo previamente serializado."""
        return joblib.load(filepath)
