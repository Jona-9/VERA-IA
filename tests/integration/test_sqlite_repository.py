"""
Pruebas de integración para SQLitePortfolioRepository.
Verifica transacciones, persistencia, cola de revisión, auditoría y
estricto cumplimiento del Principio Constitucional IV (Aislamiento temporal).
"""

from datetime import date, datetime
import os
import tempfile
import pytest

from src.data.repository import (
    CustomerDTO,
    AccountDTO,
    PeriodRecordDTO,
    PendingPaymentDTO,
)
from src.data.sqlite_repo import SQLitePortfolioRepository


@pytest.fixture
def temp_repo():
    """Fixture que provee un repositorio SQLite en un archivo temporal aislado."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name
    repo = SQLitePortfolioRepository(db_path=db_path)
    yield repo
    if os.path.exists(db_path):
        os.remove(db_path)


def test_customer_and_account_crud(temp_repo):
    """Verifica guardado y recuperación de clientes y cuentas."""
    customer = CustomerDTO(
        customer_id="CUST-00001",
        full_name="Carlos Santana",
        email="carlos.santana@demo.veraia.local",
        contact_enabled=True,
    )
    temp_repo.save_customer(customer)

    retrieved_cust = temp_repo.get_customer("CUST-00001")
    assert retrieved_cust is not None
    assert retrieved_cust.customer_id == "CUST-00001"
    assert retrieved_cust.full_name == "Carlos Santana"
    assert retrieved_cust.contact_enabled is True

    account = AccountDTO(
        account_id="ACC-00001",
        customer_id="CUST-00001",
        credit_limit=5000.0,
        current_balance=2500.0,
        minimum_payment=200.0,
        due_date=date(2026, 10, 20),
        status="PENDING_PAYMENT",
    )
    temp_repo.save_account(account)

    accounts = temp_repo.get_portfolio_accounts(cutoff_date=date(2026, 10, 15))
    assert len(accounts) == 1
    assert accounts[0].account_id == "ACC-00001"
    assert accounts[0].credit_limit == 5000.0


def test_principle_iv_no_lookahead_temporal_integrity(temp_repo):
    """
    PRUEBA CRÍTICA DE CONSTITUCIONALIDAD (Principio IV):
    Garantiza que get_period_history NUNCA retorne datos posteriores a la fecha de corte
    y enmascare pagos reales que hayan ocurrido en el futuro respecto a la fecha evaluada.
    """
    # 1. Setup cliente y cuenta
    temp_repo.save_customer(
        CustomerDTO(
            customer_id="CUST-TEMP",
            full_name="Prueba Temporal",
            email="temp@demo.veraia.local",
            contact_enabled=True,
        )
    )
    temp_repo.save_account(
        AccountDTO(
            account_id="ACC-TEMP",
            customer_id="CUST-TEMP",
            credit_limit=10000.0,
            current_balance=4000.0,
            minimum_payment=400.0,
            due_date=date(2026, 10, 18),
            status="PENDING_PAYMENT",
        )
    )

    # 2. Período 1: Pasado cerrado y pagado a tiempo (Agosto 2026)
    temp_repo.save_period_record(
        PeriodRecordDTO(
            record_id="REC-01",
            account_id="ACC-TEMP",
            period_index=0,
            billing_date=date(2026, 8, 1),
            due_date=date(2026, 8, 20),
            billed_amount=2000.0,
            paid_amount=2000.0,
            actual_payment_date=date(2026, 8, 18),
            recorded_payment_date=date(2026, 8, 19),
            days_past_due=0,
            line_utilization=0.20,
        )
    )

    # 3. Período 2: Facturado antes de corte (1 Oct), pero pagado DESPUÉS de corte (20 Oct)
    temp_repo.save_period_record(
        PeriodRecordDTO(
            record_id="REC-02",
            account_id="ACC-TEMP",
            period_index=1,
            billing_date=date(2026, 10, 1),
            due_date=date(2026, 10, 18),
            billed_amount=3000.0,
            paid_amount=3000.0,
            actual_payment_date=date(2026, 10, 20),      # PAGO EN EL FUTURO (después del corte)
            recorded_payment_date=date(2026, 10, 21),    # REGISTRO EN EL FUTURO
            days_past_due=2,
            line_utilization=0.30,
        )
    )

    # 4. Período 3: Totalmente en el futuro (Noviembre 2026)
    temp_repo.save_period_record(
        PeriodRecordDTO(
            record_id="REC-03",
            account_id="ACC-TEMP",
            period_index=2,
            billing_date=date(2026, 11, 1),              # FACTURACIÓN EN EL FUTURO
            due_date=date(2026, 11, 20),
            billed_amount=4000.0,
            paid_amount=4000.0,
            actual_payment_date=date(2026, 11, 15),
            recorded_payment_date=date(2026, 11, 16),
            days_past_due=0,
            line_utilization=0.40,
        )
    )

    cutoff = date(2026, 10, 15)
    history = temp_repo.get_period_history(account_id="ACC-TEMP", cutoff_date=cutoff)

    # Verificación 1: El período de Noviembre NO debe existir en el historial
    record_ids = [r.record_id for r in history]
    assert "REC-03" not in record_ids
    assert len(history) == 2

    # Verificación 2: El período 2 (pagado el 20 de Oct) debe enmascarar el pago futuro
    rec_02 = next(r for r in history if r.record_id == "REC-02")
    assert rec_02.actual_payment_date is None, "A fecha de corte no se debe conocer la fecha de pago futura"
    assert rec_02.paid_amount == 0.0, "A fecha de corte el pago futuro no debe computarse como realizado"


def test_pending_payments_query(temp_repo):
    """Verifica que las consultas de pagos pendientes filtren por fecha de corte y estado."""
    temp_repo.save_customer(CustomerDTO(customer_id="CUST-P", full_name="P", email="p@demo.local", contact_enabled=True))
    temp_repo.save_account(AccountDTO(account_id="ACC-P", customer_id="CUST-P", credit_limit=5000, current_balance=1000, minimum_payment=100, due_date=date(2026, 10, 20), status="PENDING_PAYMENT"))

    # Pago en trámite antes de la fecha de corte
    temp_repo.save_pending_payment(
        PendingPaymentDTO(
            payment_id="PAY-01",
            account_id="ACC-P",
            amount=500.0,
            payment_date=date(2026, 10, 14),
            status="IN_PROCESS",
        )
    )
    # Pago en trámite posterior a la fecha de corte
    temp_repo.save_pending_payment(
        PendingPaymentDTO(
            payment_id="PAY-02",
            account_id="ACC-P",
            amount=600.0,
            payment_date=date(2026, 10, 18),
            status="IN_PROCESS",
        )
    )

    cutoff = date(2026, 10, 15)
    pending = temp_repo.get_pending_payments("ACC-P", cutoff_date=cutoff)
    assert len(pending) == 1
    assert pending[0].payment_id == "PAY-01"


def test_review_queue_and_analyst_payment_update(temp_repo):
    """Verifica el flujo de la cola de revisión, corrección por analista y auditoría inmutable."""
    temp_repo.save_customer(CustomerDTO(customer_id="CUST-REV", full_name="Rev Test", email="rev@demo.local", contact_enabled=True))
    temp_repo.save_account(AccountDTO(account_id="ACC-REV", customer_id="CUST-REV", credit_limit=5000, current_balance=1500, minimum_payment=200, due_date=date(2026, 10, 20), status="PENDING_PAYMENT"))

    # Agregar dos casos a la cola con diferente urgencia (days_to_due)
    temp_repo.save_review_case({
        "case_id": "CASE-01",
        "account_id": "ACC-REV",
        "evaluation_id": "EVAL-01",
        "days_to_due": 5,
        "risk_band": "ALTA",
        "reason": "Pago en trámite no acreditado",
        "agent_hypothesis": "Pago de $500 en clearing",
        "status": "PENDING",
        "created_at": datetime.now(),
    })
    temp_repo.save_review_case({
        "case_id": "CASE-02",
        "account_id": "ACC-REV",
        "evaluation_id": "EVAL-02",
        "days_to_due": 1,  # Más urgente
        "risk_band": "CRITICA",
        "reason": "Pago con cheque retenido",
        "agent_hypothesis": "Cheque acreditado ayer",
        "status": "PENDING",
        "created_at": datetime.now(),
    })

    # La cola debe entregarse ordenada por days_to_due ASC (el más urgente primero)
    queue = temp_repo.get_review_queue()
    assert len(queue) == 2
    assert queue[0]["case_id"] == "CASE-02"
    assert queue[1]["case_id"] == "CASE-01"

    # Analista aplica corrección de pago
    temp_repo.update_payment_record(
        account_id="ACC-REV",
        payment_date=date(2026, 10, 15),
        amount=1500.0,
        actor="ANALYST_JUAN",
    )

    # Verificar que el saldo de la cuenta se actualizó y quedó en PAID
    acc = temp_repo.get_account("ACC-REV")
    assert acc.current_balance == 0.0
    assert acc.status == "PAID"

    # Resolver el caso
    temp_repo.resolve_review_case(
        case_id="CASE-02",
        actor="ANALYST_JUAN",
        resolution_notes="Pago verificado por comprobante SPEI.",
    )

    remaining_queue = temp_repo.get_review_queue()
    assert len(remaining_queue) == 1
    assert remaining_queue[0]["case_id"] == "CASE-01"

    # Verificar pista de auditoría inmutable
    audit_logs = temp_repo.get_audit_logs(account_id="ACC-REV")
    assert len(audit_logs) >= 2
    event_types = [l["event_type"] for l in audit_logs]
    assert "CORRECTION" in event_types
    assert "REVIEW_RESOLVED" in event_types
