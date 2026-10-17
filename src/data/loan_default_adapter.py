"""
Adaptador del dataset empírico de préstamos (Loan_default.csv / archive.zip) para VERAIA.
Permite:
1. Cargar y muestrear datos empíricos de préstamos (255k+ registros).
2. Mapear perfiles de préstamos a entidades completas de cartera VERAIA (Customer, Account, PeriodRecord, PendingPayment).
3. Poblar bases de datos SQLite con préstamos reales para pruebas y predicción del agente de IA.
4. Extraer vectores de señales de riesgo y targets empíricos para entrenamiento y validación de RiskModel.
"""

from __future__ import annotations

import io
import os
import random
import zipfile
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

from src.data.generator import FIRST_NAMES, LAST_NAMES
from src.data.repository import (
    AccountDTO,
    CustomerDTO,
    PendingPaymentDTO,
    PeriodRecordDTO,
)
from src.data.sqlite_repo import SQLitePortfolioRepository
from src.domain.entities import AccountStatus


DEFAULT_DATASET_PATHS = [
    Path("data/Loan_default.csv"),
    Path("/Users/jonatl9/Desktop/archive.zip"),
    Path("data/archive.zip"),
]


def find_loan_dataset(custom_path: Optional[str] = None) -> Path:
    """Encuentra la ruta accesible del dataset en CSV o archivo ZIP."""
    if custom_path:
        p = Path(custom_path)
        if p.exists():
            return p
        raise FileNotFoundError(f"No se encontró el dataset en la ruta especificada: {custom_path}")

    for candidate in DEFAULT_DATASET_PATHS:
        if candidate.exists():
            return candidate

    raise FileNotFoundError(
        "No se encontró el archivo 'Loan_default.csv' en 'data/' ni 'archive.zip' en el Desktop o data/."
    )


def load_raw_loan_dataset(
    source_path: Optional[str] = None,
    nrows: Optional[int] = None,
    sample_size: Optional[int] = None,
    random_state: int = 42,
) -> pd.DataFrame:
    """
    Carga el dataset empírico desde CSV o directamente desde el archivo ZIP sin descomprimir en disco.
    """
    resolved_path = find_loan_dataset(source_path)

    if resolved_path.suffix.lower() == ".zip":
        with zipfile.ZipFile(resolved_path, "r") as z:
            csv_names = [n for n in z.namelist() if n.endswith(".csv")]
            if not csv_names:
                raise ValueError(f"El archivo ZIP {resolved_path} no contiene ningún archivo .csv")
            target_csv = csv_names[0]
            with z.open(target_csv) as f:
                df = pd.read_csv(f, nrows=nrows)
    else:
        df = pd.read_csv(resolved_path, nrows=nrows)

    if sample_size and sample_size < len(df):
        df = df.sample(n=sample_size, random_state=random_state).reset_index(drop=True)

    return df


def _generate_synthetic_name(rng: random.Random) -> str:
    fn = rng.choice(FIRST_NAMES)
    ln1 = rng.choice(LAST_NAMES)
    ln2 = rng.choice(LAST_NAMES)
    return f"{fn} {ln1} {ln2}"


def convert_loan_to_portfolio_entities(
    loan_row: Union[pd.Series, Dict[str, Any]],
    cutoff_date: date = date(2026, 10, 15),
    rng: Optional[random.Random] = None,
    simulate_delayed_payment: bool = False,
) -> Tuple[CustomerDTO, AccountDTO, List[PeriodRecordDTO], List[PendingPaymentDTO]]:
    """
    Convierte una fila de Loan_default.csv en entidades de dominio de VERAIA
    con un historial de 6 períodos mensuales coherente con las características crediticias.
    """
    if rng is None:
        rng = random.Random(42)

    loan_id = str(loan_row.get("LoanID", "UNKNOWN")).strip()
    cust_id = f"CUST-{loan_id}"
    acc_id = f"ACC-{loan_id}"

    loan_amount = float(loan_row.get("LoanAmount", 50000.0))
    dti = float(loan_row.get("DTIRatio", 0.4))
    credit_score = int(loan_row.get("CreditScore", 600))
    interest_rate = float(loan_row.get("InterestRate", 12.0))
    loan_term = int(loan_row.get("LoanTerm", 36))
    is_default = int(loan_row.get("Default", 0)) == 1

    # Nombre y correo corporativo simulado
    full_name = _generate_synthetic_name(rng)
    email_clean = full_name.lower().replace(" ", ".")
    email = f"{email_clean}@demo.veraia.local"

    customer = CustomerDTO(
        customer_id=cust_id,
        full_name=full_name,
        email=email,
        contact_enabled=True,
        created_at=cutoff_date - timedelta(days=240),
    )

    # Límite y saldo actual a fecha de corte
    credit_limit = round(loan_amount, 2)
    if is_default:
        # En mora/riesgo: alta utilización de línea (85% a 98%) o sobregiro
        utilization = rng.uniform(0.88, 0.98)
        current_balance = round(credit_limit * utilization, 2)
        status = AccountStatus.PENDING_PAYMENT.value
    else:
        # Buen pagador: utilización moderada y controlada
        utilization = rng.uniform(0.18, 0.55)
        current_balance = round(credit_limit * utilization, 2)
        status = AccountStatus.UP_TO_DATE.value

    # Pago mínimo estimado (aprox. 5% a 10% del saldo)
    minimum_payment = round(max(50.0, current_balance * 0.08), 2)
    # Fecha de vencimiento a 5-10 días del corte
    due_date = cutoff_date + timedelta(days=rng.randint(3, 8))

    account = AccountDTO(
        account_id=acc_id,
        customer_id=cust_id,
        credit_limit=credit_limit,
        current_balance=current_balance,
        minimum_payment=minimum_payment,
        due_date=due_date,
        status=status,
    )

    # Construcción del historial de 6 meses
    records: List[PeriodRecordDTO] = []
    num_periods = 6

    for p in range(num_periods):
        # Fechas mensuales hacia atrás
        months_ago = num_periods - p
        billing_date = cutoff_date - timedelta(days=months_ago * 30)
        rec_due_date = billing_date + timedelta(days=20)

        # Monto facturado del período
        billed_amount = round(current_balance * rng.uniform(0.85, 1.05), 2)

        if is_default:
            # Evolución con deterioro: en los últimos 3 meses empieza a pagar sólo el mínimo o atrasarse
            if p >= 3:
                paid_amount = minimum_payment if rng.random() > 0.3 else round(minimum_payment * 0.7, 2)
                days_past_due = rng.randint(5, 35) if p == num_periods - 1 else rng.randint(0, 15)
                actual_pay_date = rec_due_date + timedelta(days=days_past_due)
                rec_util = min(0.99, utilization * (0.8 + 0.06 * p))
            else:
                paid_amount = billed_amount
                days_past_due = 0
                actual_pay_date = rec_due_date - timedelta(days=2)
                rec_util = utilization * 0.6
        else:
            # Comportamiento puntual
            paid_amount = billed_amount
            days_past_due = 0
            actual_pay_date = rec_due_date - timedelta(days=rng.randint(1, 4))
            rec_util = utilization * rng.uniform(0.9, 1.1)

        records.append(
            PeriodRecordDTO(
                record_id=f"REC-{acc_id}-{p}",
                account_id=acc_id,
                period_index=p,
                billing_date=billing_date,
                due_date=rec_due_date,
                billed_amount=billed_amount,
                paid_amount=paid_amount,
                actual_payment_date=actual_pay_date,
                recorded_payment_date=actual_pay_date,
                days_past_due=days_past_due,
                line_utilization=round(rec_util, 4),
            )
        )

    # Pagos pendientes en tránsito (opcional o para simular inconsistencia interbancaria)
    pending_payments: List[PendingPaymentDTO] = []
    if simulate_delayed_payment:
        pending_payments.append(
            PendingPaymentDTO(
                payment_id=f"PAY-{acc_id}-01",
                account_id=acc_id,
                amount=round(minimum_payment * 1.05, 2),
                payment_date=cutoff_date - timedelta(days=1),
                status="IN_PROCESS",
            )
        )

    return customer, account, records, pending_payments


def populate_database_from_loans(
    db_path: str,
    source_path: Optional[str] = None,
    num_accounts: int = 60,
    cutoff_date: date = date(2026, 10, 15),
    seed: int = 42,
) -> SQLitePortfolioRepository:
    """
    Puebla una base de datos SQLite con una muestra estratificada de cuentas
    reales extraídas de Loan_default.csv / archive.zip.
    Mantiene la proporción natural del dataset (aprox. 10-12% en riesgo/default).
    """
    rng = random.Random(seed)
    df = load_raw_loan_dataset(source_path=source_path, sample_size=5000, random_state=seed)

    # Muestreo estratificado: garantizar presencia de clientes en default y sin default
    n_defaults = max(1, int(round(num_accounts * 0.10)))  # ~10% de revisión humana
    n_non_defaults = num_accounts - n_defaults

    df_default = df[df["Default"] == 1].sample(n=n_defaults, random_state=seed)
    df_normal = df[df["Default"] == 0].sample(n=n_non_defaults, random_state=seed)

    selected_loans = pd.concat([df_default, df_normal]).sample(frac=1.0, random_state=seed).reset_index(drop=True)

    # Si la base de datos ya existe, reinicializarla limpiamente
    if os.path.exists(db_path):
        os.remove(db_path)

    repo = SQLitePortfolioRepository(db_path)

    # Asignar un pequeño número de inconsistencias de pago demorado (2 cuentas)
    delayed_indices = set(rng.sample(range(num_accounts), min(2, num_accounts)))

    for idx, (_, loan_row) in enumerate(selected_loans.iterrows()):
        simulate_delayed = idx in delayed_indices
        cust, acc, recs, pends = convert_loan_to_portfolio_entities(
            loan_row=loan_row,
            cutoff_date=cutoff_date,
            rng=rng,
            simulate_delayed_payment=simulate_delayed,
        )

        repo.save_customer(cust)
        repo.save_account(acc)
        for rec in recs:
            repo.save_period_record(rec)
        for pend in pends:
            repo.save_pending_payment(pend)

    return repo


def extract_features_and_targets_from_loans(
    df: pd.DataFrame,
    cutoff_date: date = date(2026, 10, 15),
    seed: int = 42,
) -> Tuple[pd.DataFrame, pd.Series]:
    """
    Genera el conjunto de entrenamiento/prueba con las 7 características de VERAIA
    (`FEATURE_COLUMNS`) y el target empírico `Default` a partir de un DataFrame de préstamos.
    """
    from src.analytics.signals import compute_signals_for_account, signal_set_to_features
    from src.domain.entities import Account, PeriodRecord

    rng = random.Random(seed)
    feature_rows = []
    targets = []

    for _, row in df.iterrows():
        _, acc_dto, rec_dtos, _ = convert_loan_to_portfolio_entities(
            loan_row=row,
            cutoff_date=cutoff_date,
            rng=rng,
            simulate_delayed_payment=False,
        )

        acc = Account(**acc_dto.model_dump())
        records = [PeriodRecord(**r.model_dump()) for r in rec_dtos]

        signals = compute_signals_for_account(acc, records, cutoff_date)
        feature_rows.append(signal_set_to_features(signals))
        targets.append(int(row["Default"]))

    X = pd.DataFrame(feature_rows)
    y = pd.Series(targets, name="target")
    return X, y
