"""
Pruebas exhaustivas de integración y auditoría para SQLitePortfolioRepository.
Verifica transacciones, contratos de protocolo, compatibilidad con entidades Pydantic,
cola de revisión priorizada, avisos, auditoría y el Principio Constitucional IV.
"""

from datetime import date, datetime, timedelta
import os
import tempfile
import pytest

from src.data.repository import (
    CustomerDTO,
    AccountDTO,
    PeriodRecordDTO,
    PendingPaymentDTO,
    PortfolioRepository,
)
from src.data.sqlite_repo import SQLitePortfolioRepository
from src.domain.entities import (
    Customer,
    Account,
    AccountStatus,
    RiskBand,
    EvidenceQuality,
    ActionType,
    RiskEvaluation,
    ContactNotice,
    Tone,
    NoticeStatus,
    ReviewCase,
    CapturedEmail,
    AuditLogEntry,
)


@pytest.fixture
def temp_repo():
    """Fixture que provee un repositorio SQLite en un archivo temporal aislado."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name
    repo = SQLitePortfolioRepository(db_path=db_path)
    yield repo
    if os.path.exists(db_path):
        os.remove(db_path)


def test_protocol_conformance(temp_repo):
    """Verifica que SQLitePortfolioRepository implemente formalmente el protocolo PortfolioRepository."""
    assert isinstance(temp_repo, PortfolioRepository), "El repositorio debe satisfacer el protocolo en tiempo de ejecución"


def test_customer_and_account_pydantic_entities(temp_repo):
    """Verifica compatibilidad bidireccional tanto con DTOs como con Entidades Pydantic de Dominio."""
    # Guardar usando Entidad Customer de dominio
    cust_entity = Customer(
        customer_id="CUST-ENT-01",
        full_name="Sofia Vergara",
        email="sofia@demo.veraia.local",
        contact_enabled=True,
        created_at=date(2025, 1, 10),
    )
    temp_repo.save_customer(cust_entity)

    # Recuperar como DTO
    retrieved = temp_repo.get_customer("CUST-ENT-01")
    assert retrieved is not None
    assert retrieved.customer_id == "CUST-ENT-01"
    assert retrieved.full_name == "Sofia Vergara"
    assert retrieved.email == "sofia@demo.veraia.local"
    assert retrieved.created_at == date(2025, 1, 10)

    # Guardar Cuenta usando Entidad Account de dominio
    acc_entity = Account(
        account_id="ACC-ENT-01",
        customer_id="CUST-ENT-01",
        credit_limit=12000.0,
        current_balance=4500.0,
        minimum_payment=360.0,
        due_date=date(2026, 10, 25),
        status=AccountStatus.UP_TO_DATE,
    )
    temp_repo.save_account(acc_entity)

    acc_dto = temp_repo.get_account("ACC-ENT-01")
    assert acc_dto is not None
    assert acc_dto.account_id == "ACC-ENT-01"
    assert acc_dto.current_balance == 4500.0


def test_principle_iv_no_lookahead_temporal_integrity(temp_repo):
    """
    PRUEBA CRÍTICA DE AUDITORÍA Y CONSTITUCIONALIDAD (Principio IV):
    Garantiza que get_period_history NUNCA retorne datos posteriores a la fecha de corte
    y enmascare pagos reales que hayan ocurrido en el futuro respecto a la fecha evaluada.
    """
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

    # Período 1: Pasado cerrado y pagado a tiempo (Agosto 2026)
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

    # Período 2: Facturado antes de corte (1 Oct), pero pagado DESPUÉS de corte (20 Oct)
    temp_repo.save_period_record(
        PeriodRecordDTO(
            record_id="REC-02",
            account_id="ACC-TEMP",
            period_index=1,
            billing_date=date(2026, 10, 1),
            due_date=date(2026, 10, 18),
            billed_amount=3000.0,
            paid_amount=3000.0,
            actual_payment_date=date(2026, 10, 20),
            recorded_payment_date=date(2026, 10, 21),
            days_past_due=2,
            line_utilization=0.30,
        )
    )

    # Período 3: Totalmente en el futuro (Noviembre 2026)
    temp_repo.save_period_record(
        PeriodRecordDTO(
            record_id="REC-03",
            account_id="ACC-TEMP",
            period_index=2,
            billing_date=date(2026, 11, 1),
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

    # Aislamiento temporal de registros futuros
    record_ids = [r.record_id for r in history]
    assert "REC-03" not in record_ids
    assert len(history) == 2

    # Aislamiento temporal de pagos no ocurridos a fecha de corte
    rec_02 = next(r for r in history if r.record_id == "REC-02")
    assert rec_02.actual_payment_date is None, "A fecha de corte no se debe conocer la fecha de pago futura"
    assert rec_02.recorded_payment_date is None, "A fecha de corte no se debe conocer la fecha contable futura"
    assert rec_02.paid_amount == 0.0, "A fecha de corte el pago futuro no debe computarse como realizado"


def test_notice_quota_and_date_separation_tracking(temp_repo):
    """Verifica que el conteo de avisos y fecha del último aviso respeten ventanas y estados."""
    temp_repo.save_customer(CustomerDTO(customer_id="CUST-NOT", full_name="Avisos", email="not@demo.local", contact_enabled=True))
    temp_repo.save_account(AccountDTO(account_id="ACC-NOT", customer_id="CUST-NOT", credit_limit=5000, current_balance=1000, minimum_payment=100, due_date=date(2026, 10, 20), status="PENDING_PAYMENT"))

    # Aviso 1: Enviado el 10 de octubre (APPROVED)
    temp_repo.save_notice(
        ContactNotice(
            notice_id="NOT-01",
            account_id="ACC-NOT",
            evaluation_id="EVAL-01",
            scheduled_date=date(2026, 10, 10),
            tone=Tone.PREVENTIVE,
            subject="Recordatorio preventivo",
            body_text="Estimado cliente...",
            status=NoticeStatus.APPROVED,
        )
    )

    # Aviso 2: Rechazado por herramienta (REJECTED) el 12 de octubre - NO debe sumar a la cuota
    temp_repo.save_notice(
        ContactNotice(
            notice_id="NOT-02",
            account_id="ACC-NOT",
            evaluation_id="EVAL-02",
            scheduled_date=date(2026, 10, 12),
            tone=Tone.FIRM,
            subject="Aviso bloqueado",
            body_text="...",
            status=NoticeStatus.REJECTED,
            rejection_reason="BLOCKED_BY_POLICY",
        )
    )

    # Aviso 3: Programado para el 14 de octubre (SCHEDULED)
    temp_repo.save_notice(
        ContactNotice(
            notice_id="NOT-03",
            account_id="ACC-NOT",
            evaluation_id="EVAL-03",
            scheduled_date=date(2026, 10, 14),
            tone=Tone.PREVENTIVE,
            subject="Segundo recordatorio",
            body_text="...",
            status=NoticeStatus.SCHEDULED,
        )
    )

    # 1. Contar avisos en el ciclo del 08 al 15 de octubre
    cnt = temp_repo.get_account_notices_count(
        account_id="ACC-NOT",
        cycle_start_date=date(2026, 10, 8),
        cutoff_date=date(2026, 10, 15),
    )
    # Deben ser 2 (NOT-01 y NOT-03), el rechazado NOT-02 no cuenta
    assert cnt == 2

    # 2. Última fecha de aviso válida
    last_date = temp_repo.get_last_notice_date("ACC-NOT")
    assert last_date == date(2026, 10, 14)


def test_review_queue_priority_ordering_and_resolution(temp_repo):
    """
    Verifica que la cola de revisión se ordene estrictamente por:
    1. Menor número de días al vencimiento (urgencia)
    2. Mayor nivel de riesgo (CRITICA > ALTA > MODERADA > BAJA)
    """
    temp_repo.save_customer(CustomerDTO(customer_id="CUST-REV", full_name="Rev Test", email="rev@demo.local", contact_enabled=True))
    temp_repo.save_account(AccountDTO(account_id="ACC-REV", customer_id="CUST-REV", credit_limit=5000, current_balance=1500, minimum_payment=200, due_date=date(2026, 10, 20), status="PENDING_PAYMENT"))

    now = datetime.now()

    # Caso A: 3 días al vencimiento, Banda MODERADA
    temp_repo.save_review_case(
        ReviewCase(
            case_id="CASE-A",
            account_id="ACC-REV",
            evaluation_id="EVAL-A",
            days_to_due=3,
            risk_band=RiskBand.MODERADA,
            reason="Caso A",
            agent_hypothesis="Hipot A",
            created_at=now,
        )
    )
    # Caso B: 3 días al vencimiento, Banda CRITICA (debe ir antes que el Caso A al tener mismo days_to_due)
    temp_repo.save_review_case(
        ReviewCase(
            case_id="CASE-B",
            account_id="ACC-REV",
            evaluation_id="EVAL-B",
            days_to_due=3,
            risk_band=RiskBand.CRITICA,
            reason="Caso B",
            agent_hypothesis="Hipot B",
            created_at=now,
        )
    )
    # Caso C: 1 día al vencimiento, Banda ALTA (debe ir de primero por tener menor days_to_due)
    temp_repo.save_review_case(
        ReviewCase(
            case_id="CASE-C",
            account_id="ACC-REV",
            evaluation_id="EVAL-C",
            days_to_due=1,
            risk_band=RiskBand.ALTA,
            reason="Caso C",
            agent_hypothesis="Hipot C",
            created_at=now,
        )
    )

    queue = temp_repo.get_review_queue()
    assert len(queue) == 3
    # Orden esperado: CASE-C (1 día), CASE-B (3 días, CRITICA), CASE-A (3 días, MODERADA)
    assert queue[0]["case_id"] == "CASE-C"
    assert queue[1]["case_id"] == "CASE-B"
    assert queue[2]["case_id"] == "CASE-A"


def test_payment_update_reconciliation_and_audit(temp_repo):
    """Verifica actualización de pago, saldo, liquidación de pendientes y pista de auditoría."""
    temp_repo.save_customer(CustomerDTO(customer_id="CUST-UPD", full_name="Update Test", email="upd@demo.local", contact_enabled=True))
    temp_repo.save_account(AccountDTO(account_id="ACC-UPD", customer_id="CUST-UPD", credit_limit=5000, current_balance=800, minimum_payment=150, due_date=date(2026, 10, 20), status="PENDING_PAYMENT"))

    # Período existente
    temp_repo.save_period_record(
        PeriodRecordDTO(
            record_id="REC-UPD-01",
            account_id="ACC-UPD",
            period_index=0,
            billing_date=date(2026, 10, 1),
            due_date=date(2026, 10, 20),
            billed_amount=800.0,
            paid_amount=0.0,
            days_past_due=0,
            line_utilization=0.16,
        )
    )

    # Pago en trámite
    temp_repo.save_pending_payment(
        PendingPaymentDTO(
            payment_id="PAY-IN-PROC",
            account_id="ACC-UPD",
            amount=800.0,
            payment_date=date(2026, 10, 15),
            status="IN_PROCESS",
        )
    )

    # Aplicar corrección por analista
    temp_repo.update_payment_record(
        account_id="ACC-UPD",
        payment_date=date(2026, 10, 15),
        amount=800.0,
        actor="ANALISTA_CAROLINA",
    )

    # 1. Saldo debe ser 0.0 y estado PAID
    acc = temp_repo.get_account("ACC-UPD")
    assert acc.current_balance == 0.0
    assert acc.status == "PAID"

    # 2. El pago pendiente debe haberse marcado CLEARED
    pending = temp_repo.get_pending_payments("ACC-UPD", cutoff_date=date(2026, 10, 16))
    assert len(pending) == 0

    # 3. Pista de auditoría inmutable
    logs = temp_repo.get_audit_logs(account_id="ACC-UPD", event_type="CORRECTION")
    assert len(logs) == 1
    assert logs[0]["actor"] == "ANALISTA_CAROLINA"
    assert logs[0]["payload"]["new_status"] == "PAID"
    assert logs[0]["payload"]["amount"] == 800.0


def test_captured_emails_flow(temp_repo):
    """Verifica almacenamiento y recuperación de correos capturados por aiosmtpd."""
    email_data = CapturedEmail(
        email_id="EML-001",
        sender="noreply@demo.veraia.local",
        recipient="cliente@demo.veraia.local",
        subject="Recordatorio de pago oportuno",
        raw_content="From: ...\nTo: ...\nSubject: ...\n\nMensaje RFC822",
        captured_at=datetime.now(),
    )
    temp_repo.save_captured_email(email_data)

    captured = temp_repo.get_captured_emails()
    assert len(captured) == 1
    assert captured[0]["email_id"] == "EML-001"
    assert captured[0]["recipient"] == "cliente@demo.veraia.local"


def test_error_handling_non_existent_records(temp_repo):
    """Verifica que llamadas con identificadores inexistentes arrojen errores controlados."""
    with pytest.raises(ValueError, match="No existe la cuenta"):
        temp_repo.update_payment_record("ACC-INEXISTENTE", date(2026, 10, 15), 100.0, "ACTOR")

    with pytest.raises(ValueError, match="Caso de revisión no encontrado"):
        temp_repo.resolve_review_case("CASE-INEXISTENTE", "ACTOR", "Notas")
