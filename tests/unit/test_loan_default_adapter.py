"""
Pruebas unitarias para el adaptador del dataset empírico de préstamos (Loan_default.csv / archive.zip).
Verifica:
- Detección de dataset en CSV y ZIP.
- Muestreo y carga en DataFrame.
- Conversión a entidades de dominio completas (Customer, Account, PeriodRecord, PendingPayment).
- Extracción determinista de señales de riesgo y targets empíricos.
- Poblado reproducible de SQLite.
"""

from datetime import date
import os
import tempfile
import pandas as pd
import pytest

from src.data.loan_default_adapter import (
    find_loan_dataset,
    load_raw_loan_dataset,
    convert_loan_to_portfolio_entities,
    populate_database_from_loans,
    extract_features_and_targets_from_loans,
)
from src.analytics.signals import FEATURE_COLUMNS


def test_find_loan_dataset():
    path = find_loan_dataset()
    assert path.exists()
    assert path.suffix.lower() in [".csv", ".zip"]


def test_load_raw_loan_dataset_sample():
    df = load_raw_loan_dataset(sample_size=25, random_state=42)
    assert len(df) == 25
    expected_cols = ["LoanID", "Age", "Income", "LoanAmount", "CreditScore", "DTIRatio", "Default"]
    for col in expected_cols:
        assert col in df.columns


def test_convert_loan_to_portfolio_entities():
    sample_row = pd.Series({
        "LoanID": "TEST1234",
        "Age": 45,
        "Income": 75000,
        "LoanAmount": 100000,
        "CreditScore": 620,
        "MonthsEmployed": 48,
        "NumCreditLines": 3,
        "InterestRate": 12.5,
        "LoanTerm": 36,
        "DTIRatio": 0.42,
        "Default": 1,
    })

    cutoff = date(2026, 10, 15)
    cust, acc, recs, pends = convert_loan_to_portfolio_entities(
        sample_row,
        cutoff_date=cutoff,
        simulate_delayed_payment=True,
    )

    assert cust.customer_id == "CUST-TEST1234"
    assert acc.account_id == "ACC-TEST1234"
    assert acc.credit_limit == 100000.0
    assert len(recs) == 6
    assert len(pends) == 1
    assert pends[0].status == "IN_PROCESS"

    # Verificar aislamiento temporal estricto (RF-03)
    for r in recs:
        assert r.billing_date <= cutoff


def test_populate_database_from_loans():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_loans.db")
        cutoff = date(2026, 10, 15)
        repo = populate_database_from_loans(
            db_path=db_path,
            num_accounts=15,
            cutoff_date=cutoff,
            seed=42,
        )

        accounts = repo.get_portfolio_accounts(cutoff)
        assert len(accounts) == 15

        first_acc = accounts[0]
        customer = repo.get_customer(first_acc.customer_id)
        assert customer is not None
        history = repo.get_period_history(first_acc.account_id, cutoff)
        assert len(history) == 6


def test_extract_features_and_targets_from_loans():
    df = load_raw_loan_dataset(sample_size=30, random_state=42)
    X, y = extract_features_and_targets_from_loans(df, cutoff_date=date(2026, 10, 15))

    assert len(X) == 30
    assert len(y) == 30
    assert list(X.columns) == list(FEATURE_COLUMNS)
    assert set(y.unique()).issubset({0, 1})
