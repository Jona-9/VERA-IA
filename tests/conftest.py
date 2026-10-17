"""
Fixtures y utilidades de prueba para la suite de pruebas de VERAIA.
Permite desarrollo desacoplado para Dev 2 (ML / Analytics).
"""

from datetime import date, timedelta
from typing import List, Tuple
import pytest
import numpy as np
import pandas as pd
from pathlib import Path
from src.policy.config import PolicyConfig, load_policy_config

from src.domain.entities import (
    Customer,
    Account,
    AccountStatus,
    PeriodRecord,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
POLICY_PATH = PROJECT_ROOT / "config" / "politica.yaml"

@pytest.fixture
def policy_config() -> PolicyConfig:
    """Política real cargada desde `config/politica.yaml` (rutas resueltas, no depende del cwd)."""
    return load_policy_config(POLICY_PATH)


@pytest.fixture
def cutoff_date() -> date:
    """Fecha de corte de referencia para evaluación."""
    return date(2026, 10, 15)


@pytest.fixture
def punctual_account_and_history(cutoff_date: date) -> Tuple[Account, List[PeriodRecord]]:
    """Cliente puntual con pagos completos y bajo uso de línea."""
    account = Account(
        account_id="ACC-PUNCTUAL-01",
        customer_id="CUST-01",
        credit_limit=10000.0,
        current_balance=1500.0,
        minimum_payment=150.0,
        due_date=date(2026, 10, 25),
        status=AccountStatus.UP_TO_DATE,
    )
    records = []
    # 6 meses anteriores
    for i in range(6, 0, -1):
        billing_d = date(2026, 10 - i, 1)
        due_d = date(2026, 10 - i, 25)
        records.append(
            PeriodRecord(
                record_id=f"REC-PUNCTUAL-{i}",
                account_id=account.account_id,
                period_index=6 - i,
                billing_date=billing_d,
                due_date=due_d,
                billed_amount=1500.0,
                paid_amount=1500.0,  # Pago total
                actual_payment_date=due_d - timedelta(days=3),
                recorded_payment_date=due_d - timedelta(days=3),
                days_past_due=0,
                line_utilization=0.15,
            )
        )
    return account, records


@pytest.fixture
def deteriorating_account_and_history(cutoff_date: date) -> Tuple[Account, List[PeriodRecord]]:
    """
    Cliente con deterioro incipiente:
    - Uso de línea escalando hasta 95%
    - Últimos 3 períodos pagando solo el mínimo
    - Caída fuerte en el monto pagado respecto a lo facturado
    - Sin atrasos graves aún (aviso temprano preventivo)
    """
    account = Account(
        account_id="ACC-DETERIORATING-01",
        customer_id="CUST-02",
        credit_limit=10000.0,
        current_balance=9500.0,
        minimum_payment=950.0,
        due_date=date(2026, 10, 25),
        status=AccountStatus.UP_TO_DATE,
    )
    records = []
    # 6 meses: primeros 3 normales, últimos 3 con deterioro
    utilizations = [0.20, 0.30, 0.40, 0.70, 0.85, 0.95]
    billed = [2000.0, 3000.0, 4000.0, 7000.0, 8500.0, 9500.0]
    paid = [2000.0, 3000.0, 4000.0, 700.0, 850.0, 950.0]  # solo mínimos los últimos 3

    for i in range(6, 0, -1):
        idx = 6 - i
        billing_d = date(2026, 10 - i, 1)
        due_d = date(2026, 10 - i, 25)
        records.append(
            PeriodRecord(
                record_id=f"REC-DET-{i}",
                account_id=account.account_id,
                period_index=idx,
                billing_date=billing_d,
                due_date=due_d,
                billed_amount=billed[idx],
                paid_amount=paid[idx],
                actual_payment_date=due_d,
                recorded_payment_date=due_d,
                days_past_due=0,
                line_utilization=utilizations[idx],
            )
        )
    return account, records


@pytest.fixture
def chronic_delinquent_account_and_history(cutoff_date: date) -> Tuple[Account, List[PeriodRecord]]:
    """Cliente con mora crónica y recurrente."""
    account = Account(
        account_id="ACC-CHRONIC-01",
        customer_id="CUST-03",
        credit_limit=5000.0,
        current_balance=4800.0,
        minimum_payment=600.0,
        due_date=date(2026, 10, 20),
        status=AccountStatus.OVERDUE,
    )
    records = []
    for i in range(5, 0, -1):
        idx = 5 - i
        billing_d = date(2026, 10 - i, 1)
        due_d = date(2026, 10 - i, 20)
        past_due = [10, 15, 25, 30, 40][idx]
        records.append(
            PeriodRecord(
                record_id=f"REC-CHRONIC-{i}",
                account_id=account.account_id,
                period_index=idx,
                billing_date=billing_d,
                due_date=due_d,
                billed_amount=4000.0,
                paid_amount=2000.0,
                actual_payment_date=due_d + timedelta(days=past_due),
                recorded_payment_date=due_d + timedelta(days=past_due + 1),
                days_past_due=past_due,
                line_utilization=0.90,
            )
        )
    return account, records


@pytest.fixture
def short_history_account_and_history(cutoff_date: date) -> Tuple[Account, List[PeriodRecord]]:
    """Cliente con historial insuficiente (< 3 períodos)."""
    account = Account(
        account_id="ACC-SHORT-01",
        customer_id="CUST-04",
        credit_limit=3000.0,
        current_balance=500.0,
        minimum_payment=50.0,
        due_date=date(2026, 10, 25),
        status=AccountStatus.UP_TO_DATE,
    )
    records = [
        PeriodRecord(
            record_id="REC-SHORT-1",
            account_id=account.account_id,
            period_index=0,
            billing_date=date(2026, 9, 1),
            due_date=date(2026, 9, 25),
            billed_amount=500.0,
            paid_amount=500.0,
            actual_payment_date=date(2026, 9, 20),
            recorded_payment_date=date(2026, 9, 20),
            days_past_due=0,
            line_utilization=0.17,
        )
    ]
    return account, records


@pytest.fixture
def future_leakage_history(cutoff_date: date) -> Tuple[Account, List[PeriodRecord]]:
    """
    Contiene registros históricos normales antes de cutoff_date (2026-10-15)
    y eventos en el futuro (después de cutoff_date) para probar que NO se filtren datos.
    """
    account = Account(
        account_id="ACC-LEAK-01",
        customer_id="CUST-05",
        credit_limit=10000.0,
        current_balance=2000.0,
        minimum_payment=200.0,
        due_date=date(2026, 10, 20),
        status=AccountStatus.UP_TO_DATE,
    )
    records = [
        # Pasado: antes de corte
        PeriodRecord(
            record_id="REC-PAST-1",
            account_id=account.account_id,
            period_index=0,
            billing_date=date(2026, 8, 1),
            due_date=date(2026, 8, 20),
            billed_amount=2000.0,
            paid_amount=2000.0,
            actual_payment_date=date(2026, 8, 18),
            recorded_payment_date=date(2026, 8, 18),
            days_past_due=0,
            line_utilization=0.20,
        ),
        PeriodRecord(
            record_id="REC-PAST-2",
            account_id=account.account_id,
            period_index=1,
            billing_date=date(2026, 9, 1),
            due_date=date(2026, 9, 20),
            billed_amount=2000.0,
            paid_amount=2000.0,
            actual_payment_date=date(2026, 9, 19),
            recorded_payment_date=date(2026, 9, 19),
            days_past_due=0,
            line_utilization=0.20,
        ),
        # Futuro: después de corte (debe ser ignorado por el extractor)
        PeriodRecord(
            record_id="REC-FUTURE-1",
            account_id=account.account_id,
            period_index=2,
            billing_date=date(2026, 10, 28),  # Posterior a 2026-10-15
            due_date=date(2026, 11, 20),
            billed_amount=8000.0,
            paid_amount=800.0,
            actual_payment_date=date(2026, 11, 20),
            recorded_payment_date=date(2026, 11, 20),
            days_past_due=45,  # Si se filtrara, inflaría artificialmente la mora a fecha de corte
            line_utilization=0.95,
        ),
    ]
    return account, records


@pytest.fixture
def synthetic_training_data() -> Tuple[pd.DataFrame, pd.Series]:
    """
    Genera un conjunto tabular de 200 observaciones con señales sintéticas y target binario
    garantizando separabilidad y reproducibilidad para pruebas del modelo.
    """
    rng = np.random.default_rng(seed=42)
    n = 200

    # Variables predictivas
    credit_utilization = rng.uniform(0.1, 0.98, size=n)
    consecutive_mins = rng.integers(0, 5, size=n)
    payment_to_billed = rng.uniform(0.1, 1.2, size=n)
    payment_ratio_drop = rng.uniform(0.0, 0.8, size=n)
    hist_delinquency_rate = rng.uniform(0.0, 0.7, size=n)
    max_past_due = rng.integers(0, 45, size=n)
    delinquency_trend = rng.uniform(-10.0, 20.0, size=n)

    # Log-odds con coeficientes coherentes de riesgo
    log_odds = (
        -3.5
        + 3.5 * credit_utilization
        + 0.8 * consecutive_mins
        - 2.0 * payment_to_billed
        + 2.5 * payment_ratio_drop
        + 3.0 * hist_delinquency_rate
        + 0.05 * max_past_due
        + 0.08 * delinquency_trend
    )
    probs = 1 / (1 + np.exp(-log_odds))
    y = rng.binomial(1, probs)

    X = pd.DataFrame(
        {
            "credit_utilization_ratio": credit_utilization,
            "consecutive_min_payments": consecutive_mins,
            "payment_to_billed_ratio": payment_to_billed,
            "payment_ratio_drop": payment_ratio_drop,
            "historical_delinquency_rate": hist_delinquency_rate,
            "max_past_due_days": max_past_due,
            "delinquency_trend": delinquency_trend,
        }
    )
    return X, pd.Series(y, name="target")
