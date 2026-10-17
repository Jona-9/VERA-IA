"""
Generador sintético reproducible de cartera crediticia con semilla fija.
Cumple con FR-001: perfiles de clientes estables, deterioro incipiente,
moras crónicas, inconsistencias de pago demorado y clientes nuevos.
"""

from datetime import date, timedelta
import random
from typing import List, Dict, Any, Optional, Tuple
import uuid

from src.data.repository import (
    CustomerDTO,
    AccountDTO,
    PeriodRecordDTO,
    PendingPaymentDTO,
)
from src.data.sqlite_repo import SQLitePortfolioRepository


# Nombres y apellidos hispanos para realismo en la demo
FIRST_NAMES = [
    "Carlos", "Sofia", "Alejandro", "Valentina", "Mateo", "Camila",
    "Diego", "Lucia", "Javier", "Mariana", "Andres", "Isabella",
    "Gabriel", "Daniela", "Santiago", "Elena", "Lucas", "Paula",
    "Leonardo", "Natalia", "Joaquin", "Valeria", "Emilio", "Fernanda"
]

LAST_NAMES = [
    "Hernandez", "Garcia", "Martinez", "Lopez", "Gonzalez", "Rodriguez",
    "Perez", "Sanchez", "Ramirez", "Flores", "Torres", "Diaz",
    "Vargas", "Morales", "Castillo", "Ortiz", "Reyes", "Mendoza",
    "Silva", "Guzman", "Romero", "Navarro", "Ramos", "Salazar"
]


class PortfolioGenerator:
    """
    Genera carteras reproducibles asegurando la presencia de perfiles específicos
    requeridos para evaluar el comportamiento del agente de cobranza temprana.
    """

    def __init__(self, seed: int = 42, cutoff_date: Optional[date] = None):
        self.seed = seed
        self.cutoff_date = cutoff_date or date(2026, 10, 15)
        self.rng = random.Random(seed)

    def _generate_customer_name(self, index: int) -> str:
        fn = self.rng.choice(FIRST_NAMES)
        ln1 = self.rng.choice(LAST_NAMES)
        ln2 = self.rng.choice(LAST_NAMES)
        return f"{fn} {ln1} {ln2}"

    def generate_portfolio(
        self, num_customers: int = 60
    ) -> Tuple[List[CustomerDTO], List[AccountDTO], List[PeriodRecordDTO], List[PendingPaymentDTO]]:
        """
        Genera clientes, cuentas, registros históricos y pagos pendientes.
        Distribución de perfiles:
        - 40% Estables (buen comportamiento, utilización moderada)
        - 25% Deterioro incipiente (señal clave: pagos mínimos sostenidos >= 3, uso > 90%)
        - 15% Moras crónicas (retrasos recurrentes)
        - 10% Inconsistencias de pago demorado (pago emitido en tránsito interbancario)
        - 10% Clientes nuevos (< 3 períodos de historial para prueba de evidencia insuficiente)
        """
        # Reiniciar generador para garantizar determinismo estricto
        self.rng = random.Random(self.seed)

        customers: List[CustomerDTO] = []
        accounts: List[AccountDTO] = []
        periods: List[PeriodRecordDTO] = []
        pending_payments: List[PendingPaymentDTO] = []

        n_stable = int(num_customers * 0.40)
        n_deterioration = int(num_customers * 0.25)
        n_chronic = int(num_customers * 0.15)
        n_delayed = int(num_customers * 0.10)
        n_new = num_customers - (n_stable + n_deterioration + n_chronic + n_delayed)

        profile_assignments = (
            ["STABLE"] * n_stable
            + ["DETERIORATION"] * n_deterioration
            + ["CHRONIC"] * n_chronic
            + ["DELAYED_PAYMENT"] * n_delayed
            + ["NEW_CLIENT"] * n_new
        )

        # Barajar perfiles de manera determinista
        self.rng.shuffle(profile_assignments)

        for i, profile in enumerate(profile_assignments):
            cust_id = f"CUST-{i+1:05d}"
            acc_id = f"ACC-{i+1:05d}"
            full_name = self._generate_customer_name(i)
            email_handle = full_name.lower().replace(" ", ".")
            email = f"{email_handle}@demo.veraia.local"

            # 1. Crear Cliente
            customer = CustomerDTO(
                customer_id=cust_id,
                full_name=full_name,
                email=email,
                contact_enabled=True,
            )
            customers.append(customer)

            # 2. Configurar Cuenta según perfil
            limit = self.rng.choice([3000.0, 5000.0, 8000.0, 10000.0, 15000.0])
            
            # Fechas de vencimiento corriente distribuidas en torno a la fecha de corte:
            # Ventana: desde corte - 2 días hasta corte + 10 días
            days_offset = self.rng.randint(-2, 10)
            current_due_date = self.cutoff_date + timedelta(days=days_offset)

            # Configuración de historia y balances según perfil
            if profile == "NEW_CLIENT":
                # Historial corto: 1 o 2 períodos
                num_periods = self.rng.choice([1, 2])
                balance = limit * self.rng.uniform(0.3, 0.6)
                min_pay = round(balance * 0.08, 2)
                acc_status = "PENDING_PAYMENT"
            elif profile == "STABLE":
                num_periods = 6
                balance = limit * self.rng.uniform(0.15, 0.45)
                min_pay = round(balance * 0.08, 2)
                acc_status = "PENDING_PAYMENT"
            elif profile == "DETERIORATION":
                num_periods = 6
                # Deterioro temprano: alta utilización (90%-98%)
                balance = limit * self.rng.uniform(0.90, 0.98)
                min_pay = round(balance * 0.10, 2)
                acc_status = "PENDING_PAYMENT"
            elif profile == "CHRONIC":
                num_periods = 6
                balance = limit * self.rng.uniform(0.85, 0.95)
                min_pay = round(balance * 0.12, 2)
                acc_status = "OVERDUE" if days_offset < 0 else "PENDING_PAYMENT"
            elif profile == "DELAYED_PAYMENT":
                num_periods = 6
                balance = limit * self.rng.uniform(0.40, 0.70)
                min_pay = round(balance * 0.08, 2)
                acc_status = "PENDING_PAYMENT"
            else:
                num_periods = 6
                balance = limit * 0.3
                min_pay = round(balance * 0.08, 2)
                acc_status = "PENDING_PAYMENT"

            account = AccountDTO(
                account_id=acc_id,
                customer_id=cust_id,
                credit_limit=limit,
                current_balance=round(balance, 2),
                minimum_payment=min_pay,
                due_date=current_due_date,
                status=acc_status,
            )
            accounts.append(account)

            # 3. Generar Historial de Períodos hacia atrás
            # Período t-1, t-2, ...
            for p_idx in range(num_periods):
                # Cada período retrocede 30 días respecto al ciclo corriente
                period_due = current_due_date - timedelta(days=30 * (num_periods - p_idx))
                period_billing = period_due - timedelta(days=20)
                
                # Proteger que el billing_date sea siempre anterior al corte
                if period_billing > self.cutoff_date:
                    continue

                if profile == "STABLE":
                    billed = limit * self.rng.uniform(0.2, 0.4)
                    paid = billed  # Paga el 100%
                    actual_pay = period_due - timedelta(days=self.rng.randint(1, 5))
                    rec_pay = actual_pay + timedelta(days=1)
                    dpd = 0
                    util = billed / limit

                elif profile == "DETERIORATION":
                    # Deterioro progresivo: en los primeros meses paga bien, en los últimos >=3 meses paga solo el mínimo
                    if p_idx < num_periods - 3:
                        billed = limit * self.rng.uniform(0.4, 0.6)
                        paid = billed * 0.9
                        actual_pay = period_due - timedelta(days=2)
                        rec_pay = actual_pay + timedelta(days=1)
                        dpd = 0
                        util = billed / limit
                    else:
                        # Últimos períodos: pagos mínimos sostenidos y aumento de saldo
                        billed = limit * self.rng.uniform(0.85, 0.95)
                        paid = round(billed * 0.08, 2)  # Pago mínimo exacto
                        actual_pay = period_due + timedelta(days=self.rng.choice([0, 1]))
                        rec_pay = actual_pay + timedelta(days=1)
                        dpd = max(0, (actual_pay - period_due).days)
                        util = billed / limit

                elif profile == "CHRONIC":
                    billed = limit * self.rng.uniform(0.7, 0.9)
                    paid = billed * self.rng.uniform(0.3, 0.7)
                    delay_days = self.rng.randint(12, 35)
                    actual_pay = period_due + timedelta(days=delay_days)
                    rec_pay = actual_pay + timedelta(days=2)
                    dpd = delay_days
                    util = billed / limit

                elif profile == "DELAYED_PAYMENT":
                    billed = limit * self.rng.uniform(0.3, 0.5)
                    paid = billed
                    actual_pay = period_due - timedelta(days=self.rng.randint(1, 3))
                    rec_pay = actual_pay + timedelta(days=1)
                    dpd = 0
                    util = billed / limit

                elif profile == "NEW_CLIENT":
                    billed = limit * self.rng.uniform(0.3, 0.5)
                    paid = billed
                    actual_pay = period_due - timedelta(days=2)
                    rec_pay = actual_pay + timedelta(days=1)
                    dpd = 0
                    util = billed / limit

                periods.append(
                    PeriodRecordDTO(
                        record_id=f"REC-{acc_id}-{p_idx:02d}",
                        account_id=acc_id,
                        period_index=p_idx,
                        billing_date=period_billing,
                        due_date=period_due,
                        billed_amount=round(billed, 2),
                        paid_amount=round(paid, 2),
                        actual_payment_date=actual_pay,
                        recorded_payment_date=rec_pay,
                        days_past_due=dpd,
                        line_utilization=round(util, 4),
                    )
                )

            # 4. Inconsistencias de pago en trámite (para perfil DELAYED_PAYMENT)
            if profile == "DELAYED_PAYMENT":
                # Pago realizado hace 1 o 2 días que aún está en compensación interbancaria
                pay_date = self.cutoff_date - timedelta(days=self.rng.randint(1, 2))
                pending_payments.append(
                    PendingPaymentDTO(
                        payment_id=f"PAY-{acc_id}-PEND",
                        account_id=acc_id,
                        amount=min_pay * self.rng.uniform(1.0, 1.5),
                        payment_date=pay_date,
                        status="IN_PROCESS",
                    )
                )

        return customers, accounts, periods, pending_payments

    def populate_database(self, db_path: str = "data/portfolio_demo.db", num_customers: int = 60) -> SQLitePortfolioRepository:
        """Genera el dataset y lo persiste de inmediato en la base SQLite indicada."""
        repo = SQLitePortfolioRepository(db_path=db_path)
        customers, accounts, periods, pending_payments = self.generate_portfolio(num_customers=num_customers)

        for c in customers:
            repo.save_customer(c)

        for a in accounts:
            repo.save_account(a)

        for p in periods:
            repo.save_period_record(p)

        for pay in pending_payments:
            repo.save_pending_payment(pay)

        return repo
