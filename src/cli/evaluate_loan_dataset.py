"""
CLI para evaluación, prueba y predicción del agente de IA sobre el dataset empírico Loan_default.csv.
Ejecución: python -m src.cli.evaluate_loan_dataset [--csv data/Loan_default.csv] [--samples 100] [--populate-db]
"""

from __future__ import annotations

import argparse
from datetime import date
import json
import os
from pathlib import Path
from typing import List, Dict, Any

import numpy as np
import pandas as pd
from sklearn.metrics import classification_report, roc_auc_score, confusion_matrix

from src.analytics.model import RiskModel
from src.analytics.signals import compute_signals_for_account, signal_set_to_features
from src.data.loan_default_adapter import (
    convert_loan_to_portfolio_entities,
    find_loan_dataset,
    load_raw_loan_dataset,
    populate_database_from_loans,
)
from src.domain.entities import Account, PeriodRecord, RiskBand
from src.policy.config import load_policy_config
from src.policy.engine import classify_risk_band


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluación y predicción del agente de IA sobre el dataset empírico de préstamos."
    )
    parser.add_argument(
        "--csv",
        "--dataset",
        dest="dataset_path",
        type=str,
        default=None,
        help="Ruta a Loan_default.csv o archive.zip.",
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=60,
        help="Número de préstamos a evaluar en el lote de prueba.",
    )
    parser.add_argument(
        "--model-path",
        type=str,
        default="reports/risk_model.joblib",
        help="Ruta al modelo calibrado guardado.",
    )
    parser.add_argument(
        "--policy-path",
        type=str,
        default="config/politica.yaml",
        help="Ruta a la configuración de política.",
    )
    parser.add_argument(
        "--populate-db",
        action="store_true",
        help="Si se activa, puebla data/portfolio_demo.db con las cuentas evaluadas del dataset.",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default="data/portfolio_demo.db",
        help="Ruta a la base de datos a poblar si --populate-db está activo.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Semilla determinista para muestreo.",
    )
    args = parser.parse_args()

    cutoff_date = date(2026, 10, 15)

    print("=" * 80)
    print("  VERA - EVALUACIÓN Y PREDICCIÓN DEL AGENTE DE IA EN DATASET DE PRÉSTAMOS")
    print("=" * 80)

    # 1. Localizar y cargar muestra de préstamos
    dataset_file = find_loan_dataset(args.dataset_path)
    print(f"[*] Dataset detectado: {dataset_file}")
    df = load_raw_loan_dataset(source_path=str(dataset_file), sample_size=args.samples, random_state=args.seed)
    print(f"[*] Lote de prueba cargado: {len(df)} préstamos para predicción.")

    # 2. Cargar modelo calibrado y política
    if not os.path.exists(args.model_path):
        print(f"[!] Modelo {args.model_path} no encontrado. Entrenando modelo con datos del dataset...")
        os.system(f".venv/bin/python -m src.cli.train_model --loan-dataset {dataset_file} --dataset-samples 2000")

    model = RiskModel.load(args.model_path)
    policy = load_policy_config(args.policy_path)

    # 3. Evaluar cada préstamo con las herramientas y señales del agente
    predictions: List[Dict[str, Any]] = []
    y_true: List[int] = []
    y_probs: List[float] = []

    for _, row in df.iterrows():
        cust, acc_dto, rec_dtos, pends = convert_loan_to_portfolio_entities(
            loan_row=row,
            cutoff_date=cutoff_date,
        )
        acc = Account(**acc_dto.model_dump())
        records = [PeriodRecord(**r.model_dump()) for r in rec_dtos]

        # Extraer señales a fecha de corte (Principio IV: No-lookahead)
        signals = compute_signals_for_account(acc, records, cutoff_date)

        # Predicción del modelo analítico (Regresión Logística + Platt Scaling)
        raw_prob, calib_prob = model.evaluate_signals(signals)

        # Clasificación en banda de riesgo según política institucional
        band = classify_risk_band(calib_prob, policy)

        # Acción recomendada del agente
        if band == RiskBand.BAJA:
            action = "NO_ACTION"
            decision_text = "Sin acción requerida (cliente al día y bajo riesgo)"
        elif band == RiskBand.MODERADA:
            action = "SCHEDULE_NOTICE"
            decision_text = "Aviso preventivo autorizado (tono preventivo)"
        elif band == RiskBand.ALTA:
            action = "SCHEDULE_NOTICE"
            decision_text = "Aviso preventivo firme autorizado (tono firme)"
        else:  # CRITICA
            action = "ESCALATE_HUMAN"
            decision_text = "Derivar a revisión humana (riesgo crítico o mora incipiente)"

        actual_default = int(row["Default"])
        y_true.append(actual_default)
        y_probs.append(calib_prob)

        predictions.append(
            {
                "loan_id": row["LoanID"],
                "customer_name": cust.full_name,
                "loan_amount": float(row["LoanAmount"]),
                "credit_score": int(row["CreditScore"]),
                "dti_ratio": float(row["DTIRatio"]),
                "actual_default": actual_default,
                "calibrated_prob": round(calib_prob, 4),
                "risk_band": band.value,
                "action": action,
                "decision_text": decision_text,
            }
        )

    # 4. Mostrar resumen en tabla
    print("\n" + "-" * 80)
    print(f"{'Loan ID':<12} | {'Score':<5} | {'DTI':<5} | {'Monto':<10} | {'P(Default)':<10} | {'Banda':<9} | {'Acción Agente'}")
    print("-" * 80)

    # Mostrar primeros 15 casos
    for p in predictions[:15]:
        print(
            f"{p['loan_id']:<12} | {p['credit_score']:<5} | {p['dti_ratio']:<5.2f} | "
            f"${p['loan_amount']:<9,.0f} | {p['calibrated_prob']:<10.2%} | {p['risk_band']:<9} | {p['action']}"
        )

    if len(predictions) > 15:
        print(f"... y {len(predictions) - 15} préstamos más evaluados.")

    # 5. Distribución de decisiones del agente
    bands_series = pd.Series([p["risk_band"] for p in predictions])
    actions_series = pd.Series([p["action"] for p in predictions])

    print("\n" + "=" * 80)
    print("  DISTRIBUCIÓN DE CASOS Y DECISIONES DEL AGENTE")
    print("=" * 80)
    print("[*] Bandas de riesgo asignadas:")
    for band_name, count in bands_series.value_counts().items():
        pct = count / len(predictions) * 100
        print(f"    - {band_name:<10}: {count:>3} clientes ({pct:>5.1f}%)")

    print("\n[*] Acciones autorizadas por política:")
    for act_name, count in actions_series.value_counts().items():
        pct = count / len(predictions) * 100
        print(f"    - {act_name:<16}: {count:>3} clientes ({pct:>5.1f}%)")

    # Si hay suficientes clases distintas, calcular ROC-AUC
    if len(set(y_true)) > 1:
        auc = roc_auc_score(y_true, y_probs)
        print(f"\n[*] Desempeño predictivo sobre la muestra:")
        print(f"    - ROC-AUC empírico : {auc:.4f}")
        print(f"    - Total en Default : {sum(y_true)} de {len(y_true)} ({sum(y_true)/len(y_true):.1%})")

    # 6. Poblar base de datos SQLite si el usuario lo solicitó
    if args.populate_db:
        print(f"\n[*] Poblando base de datos '{args.db_path}' con {args.samples} préstamos reales del dataset...")
        populate_database_from_loans(
            db_path=args.db_path,
            source_path=str(dataset_file),
            num_accounts=args.samples,
            cutoff_date=cutoff_date,
            seed=args.seed,
        )
        print(f"[+] Base de datos {args.db_path} actualizada exitosamente con datos del dataset.")
        print("[*] Ahora puedes reiniciar o recargar el dashboard para ver los clientes reales.")

    print("=" * 80)


if __name__ == "__main__":
    main()
