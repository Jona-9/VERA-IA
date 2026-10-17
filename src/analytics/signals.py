"""
Extracción y cálculo de señales cuantitativas a fecha de corte para VERAIA.
Garantiza aislamiento temporal estricto (no-lookahead) conforme a RF-03.
"""

from datetime import date
from typing import List, Dict, Any, Optional
import numpy as np
import pandas as pd

from src.domain.entities import Account, PeriodRecord, SignalSet


def compute_signals_for_account(
    account: Account,
    history: List[PeriodRecord],
    cutoff_date: date,
) -> SignalSet:
    """
    Calcula el conjunto estricto de señales de riesgo para una cuenta a una fecha de corte dada.

    Reglas inviolables:
    1. Aislamiento temporal: se descarta cualquier registro con billing_date posterior a cutoff_date.
    2. Manejo seguro de casos con historial corto (< 3 períodos).
    """
    # 1. Aislamiento temporal estricto (No-lookahead)
    valid_records = [r for r in history if r.billing_date <= cutoff_date]
    valid_records.sort(key=lambda r: (r.billing_date, r.period_index))

    # 2. Ratio de utilización de línea a fecha de corte
    if account.credit_limit > 0:
        utilization = float(account.current_balance / account.credit_limit)
    elif valid_records:
        utilization = float(valid_records[-1].line_utilization)
    else:
        utilization = 0.0

    if not valid_records:
        return SignalSet(
            account_id=account.account_id,
            cutoff_date=cutoff_date,
            credit_utilization_ratio=round(utilization, 4),
            consecutive_min_payments=0,
            payment_to_billed_ratio=1.0,
            payment_ratio_drop=0.0,
            historical_delinquency_rate=0.0,
            max_past_due_days=0,
            delinquency_trend=0.0,
        )

    # 3. Conteo de pagos mínimos consecutivos hacia atrás desde el período más reciente
    # Un pago se considera "mínimo" si el cliente pagó sólo una fracción baja del total
    # facturado (<= 15% o muy cercano al pago mínimo pactado) habiendo saldo mayor.
    consecutive_mins = 0
    for rec in reversed(valid_records):
        if rec.billed_amount <= 0:
            break

        paid_ratio = rec.paid_amount / rec.billed_amount
        is_min_payment = False

        # Si pagó sustancialmente menos de lo facturado
        if paid_ratio < 0.95:
            # Criterio: pagó alrededor del mínimo pactado o <= 15% de lo facturado
            if account.minimum_payment > 0 and rec.paid_amount <= (account.minimum_payment * 1.10):
                is_min_payment = True
            elif paid_ratio <= 0.15:
                is_min_payment = True

        if is_min_payment:
            consecutive_mins += 1
        else:
            break

    # 4. Ratio de pago en el último período cerrado
    last_record = valid_records[-1]
    if last_record.billed_amount > 0:
        last_payment_ratio = float(min(1.0, max(0.0, last_record.paid_amount / last_record.billed_amount)))
    else:
        last_payment_ratio = 1.0

    # 5. Caída porcentual en el monto o ratio pagado respecto al promedio histórico anterior
    if len(valid_records) > 1:
        prev_ratios = [
            (r.paid_amount / r.billed_amount)
            for r in valid_records[:-1]
            if r.billed_amount > 0
        ]
        if prev_ratios:
            baseline_ratio = float(np.mean(prev_ratios))
            if baseline_ratio > 0 and last_payment_ratio < baseline_ratio:
                ratio_drop = float((baseline_ratio - last_payment_ratio) / baseline_ratio)
            else:
                ratio_drop = 0.0
        else:
            ratio_drop = 0.0
    else:
        ratio_drop = 0.0

    # 6. Tasa de atraso histórico y días máximos de mora
    delinquent_periods = [r for r in valid_records if r.days_past_due >= 1]
    hist_delinquency_rate = float(len(delinquent_periods) / len(valid_records))
    max_past_due = int(max(r.days_past_due for r in valid_records))

    # 7. Tendencia de mora (diferencia entre atraso reciente y períodos anteriores)
    if len(valid_records) >= 3:
        recent_dpd = float(np.mean([r.days_past_due for r in valid_records[-2:]]))
        older_dpd = float(np.mean([r.days_past_due for r in valid_records[:-2]]))
        delinquency_trend = float(recent_dpd - older_dpd)
    elif len(valid_records) == 2:
        delinquency_trend = float(valid_records[1].days_past_due - valid_records[0].days_past_due)
    else:
        delinquency_trend = 0.0

    return SignalSet(
        account_id=account.account_id,
        cutoff_date=cutoff_date,
        credit_utilization_ratio=round(utilization, 4),
        consecutive_min_payments=consecutive_mins,
        payment_to_billed_ratio=round(last_payment_ratio, 4),
        payment_ratio_drop=round(max(0.0, ratio_drop), 4),
        historical_delinquency_rate=round(hist_delinquency_rate, 4),
        max_past_due_days=max_past_due,
        delinquency_trend=round(delinquency_trend, 4),
    )


def signal_set_to_features(signals: SignalSet) -> Dict[str, float]:
    """Convierte un objeto SignalSet en un vector de características numéricas explicables."""
    return {
        "credit_utilization_ratio": float(signals.credit_utilization_ratio),
        "consecutive_min_payments": float(signals.consecutive_min_payments),
        "payment_to_billed_ratio": float(signals.payment_to_billed_ratio),
        "payment_ratio_drop": float(signals.payment_ratio_drop),
        "historical_delinquency_rate": float(signals.historical_delinquency_rate),
        "max_past_due_days": float(signals.max_past_due_days),
        "delinquency_trend": float(signals.delinquency_trend),
    }


FEATURE_COLUMNS = [
    "credit_utilization_ratio",
    "consecutive_min_payments",
    "payment_to_billed_ratio",
    "payment_ratio_drop",
    "historical_delinquency_rate",
    "max_past_due_days",
    "delinquency_trend",
]
