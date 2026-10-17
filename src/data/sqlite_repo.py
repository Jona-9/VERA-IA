"""
Implementación concreta de PortfolioRepository utilizando SQLite local.
Garantiza transacciones seguras, tipado estricto con DTOs y cumplimiento
del Principio Constitucional IV (Integridad temporal sin fuga de datos).
"""

from datetime import date, datetime
import json
import sqlite3
from typing import List, Optional, Dict, Any, Union
import uuid

from src.data.repository import (
    CustomerDTO,
    AccountDTO,
    PeriodRecordDTO,
    PendingPaymentDTO,
    PortfolioRepository,
)


def _parse_date(val: Any) -> Optional[date]:
    if val is None:
        return None
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, str):
        val = val.strip()
        if not val:
            return None
        return date.fromisoformat(val[:10])
    return None


def _format_date(val: Any) -> Optional[str]:
    if val is None:
        return None
    if isinstance(val, (date, datetime)):
        return val.strftime("%Y-%m-%d")
    if isinstance(val, str):
        return val[:10]
    return str(val)


def _format_datetime(val: Any) -> str:
    if val is None:
        return datetime.now().isoformat()
    if isinstance(val, datetime):
        return val.isoformat()
    if isinstance(val, date):
        return datetime.combine(val, datetime.min.time()).isoformat()
    return str(val)


class SQLitePortfolioRepository(PortfolioRepository):
    """
    Repositorio SQLite local para la gestión de cartera, historial,
    evaluaciones, cola de revisión, despachos y auditoría.
    """

    def __init__(self, db_path: str = "data/portfolio_demo.db"):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _init_db(self) -> None:
        """Crea las tablas e índices si no existen."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 1. Clientes
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS customers (
                    customer_id TEXT PRIMARY KEY,
                    full_name TEXT NOT NULL,
                    email TEXT NOT NULL,
                    contact_enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                );
                """
            )

            # 2. Cuentas
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS accounts (
                    account_id TEXT PRIMARY KEY,
                    customer_id TEXT NOT NULL,
                    credit_limit REAL NOT NULL,
                    current_balance REAL NOT NULL,
                    minimum_payment REAL NOT NULL,
                    due_date TEXT NOT NULL,
                    status TEXT NOT NULL,
                    FOREIGN KEY(customer_id) REFERENCES customers(customer_id)
                );
                """
            )

            # 3. Historial de Períodos
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS period_records (
                    record_id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    period_index INTEGER NOT NULL,
                    billing_date TEXT NOT NULL,
                    due_date TEXT NOT NULL,
                    billed_amount REAL NOT NULL,
                    paid_amount REAL NOT NULL,
                    actual_payment_date TEXT,
                    recorded_payment_date TEXT,
                    days_past_due INTEGER NOT NULL,
                    line_utilization REAL NOT NULL,
                    FOREIGN KEY(account_id) REFERENCES accounts(account_id)
                );
                """
            )

            # 4. Pagos Pendientes / En Proceso
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS pending_payments (
                    payment_id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    amount REAL NOT NULL,
                    payment_date TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'IN_PROCESS',
                    FOREIGN KEY(account_id) REFERENCES accounts(account_id)
                );
                """
            )

            # 5. Evaluaciones de Riesgo
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS risk_evaluations (
                    evaluation_id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    evaluation_date TEXT NOT NULL,
                    raw_probability REAL NOT NULL,
                    calibrated_probability REAL NOT NULL,
                    risk_band TEXT NOT NULL,
                    previous_risk_band TEXT,
                    band_change_confirmed INTEGER NOT NULL DEFAULT 0,
                    evidence_quality TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    rule_applied TEXT NOT NULL,
                    explanation TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(account_id) REFERENCES accounts(account_id)
                );
                """
            )

            # 6. Avisos de Contacto Programados y Despachados
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS contact_notices (
                    notice_id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    evaluation_id TEXT,
                    channel TEXT NOT NULL DEFAULT 'EMAIL',
                    scheduled_date TEXT NOT NULL,
                    scheduled_time TEXT NOT NULL DEFAULT '10:00:00',
                    tone TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    body_text TEXT NOT NULL,
                    validation_status TEXT NOT NULL DEFAULT 'PASSED',
                    status TEXT NOT NULL DEFAULT 'SCHEDULED',
                    rejection_reason TEXT,
                    sent_at TEXT,
                    FOREIGN KEY(account_id) REFERENCES accounts(account_id)
                );
                """
            )

            # 7. Cola de Revisión Humana
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS review_queue (
                    case_id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    evaluation_id TEXT,
                    days_to_due INTEGER NOT NULL,
                    risk_band TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    agent_hypothesis TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    corrected_data TEXT,
                    resolved_by TEXT,
                    resolved_at TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(account_id) REFERENCES accounts(account_id)
                );
                """
            )

            # 8. Correos Capturados por Servidor SMTP Local
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS captured_emails (
                    email_id TEXT PRIMARY KEY,
                    sender TEXT NOT NULL,
                    recipient TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    raw_content TEXT NOT NULL,
                    captured_at TEXT NOT NULL
                );
                """
            )

            # 9. Pista de Auditoría Inmutable
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_logs (
                    log_id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                """
            )

            # Índices de optimización de consultas frecuentes
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_period_acc_billing ON period_records(account_id, billing_date);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_pending_acc_date ON pending_payments(account_id, payment_date);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_notices_acc_date ON contact_notices(account_id, scheduled_date);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_review_status_due ON review_queue(status, days_to_due);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_eval_acc_date ON risk_evaluations(account_id, evaluation_date);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_acc_time ON audit_logs(account_id, timestamp);")

            conn.commit()

    # =========================================================================
    # Métodos del Protocolo PortfolioRepository
    # =========================================================================

    def get_portfolio_accounts(self, cutoff_date: date) -> List[AccountDTO]:
        """Obtiene todas las cuentas activas a ser evaluadas a la fecha de corte."""
        cutoff_str = _format_date(cutoff_date)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT a.account_id, a.customer_id, a.credit_limit, a.current_balance,
                       a.minimum_payment, a.due_date, a.status
                FROM accounts a
                JOIN customers c ON a.customer_id = c.customer_id
                ORDER BY a.account_id ASC;
                """
            )
            rows = cursor.fetchall()
            return [
                AccountDTO(
                    account_id=r["account_id"],
                    customer_id=r["customer_id"],
                    credit_limit=float(r["credit_limit"]),
                    current_balance=float(r["current_balance"]),
                    minimum_payment=float(r["minimum_payment"]),
                    due_date=_parse_date(r["due_date"]),
                    status=r["status"],
                )
                for r in rows
            ]

    def get_customer(self, customer_id: str) -> Optional[CustomerDTO]:
        """Obtiene los datos de contacto y consentimiento del cliente."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT customer_id, full_name, email, contact_enabled
                FROM customers
                WHERE customer_id = ?;
                """,
                (customer_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return CustomerDTO(
                customer_id=row["customer_id"],
                full_name=row["full_name"],
                email=row["email"],
                contact_enabled=bool(row["contact_enabled"]),
            )

    def get_period_history(self, account_id: str, cutoff_date: date) -> List[PeriodRecordDTO]:
        """
        Obtiene el historial cronológico de períodos cerrado estrictamente a la fecha de corte.
        PROHIBIDO retornar datos posteriores a cutoff_date (Principio Constitucional IV).
        Si el pago real se produjo después de cutoff_date, se enmascara para evitar lookahead bias.
        """
        cutoff_str = _format_date(cutoff_date)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT record_id, account_id, period_index, billing_date, due_date,
                       billed_amount, paid_amount, actual_payment_date,
                       recorded_payment_date, days_past_due, line_utilization
                FROM period_records
                WHERE account_id = ? AND billing_date <= ?
                ORDER BY period_index ASC;
                """,
                (account_id, cutoff_str),
            )
            rows = cursor.fetchall()

            history: List[PeriodRecordDTO] = []
            for r in rows:
                actual_pay_date = _parse_date(r["actual_payment_date"])
                recorded_pay_date = _parse_date(r["recorded_payment_date"])
                paid_amt = float(r["paid_amount"])
                dpd = int(r["days_past_due"])

                # Blindaje temporal estricto (Principio IV):
                # Si el pago ocurrió o se registró con posterioridad a la fecha de corte,
                # para la fecha de corte dicho pago aún no existía en los hechos.
                if actual_pay_date and actual_pay_date > cutoff_date:
                    actual_pay_date = None
                    recorded_pay_date = None
                    paid_amt = 0.0
                    period_due = _parse_date(r["due_date"])
                    dpd = max(0, (cutoff_date - period_due).days) if period_due else 0

                history.append(
                    PeriodRecordDTO(
                        record_id=r["record_id"],
                        account_id=r["account_id"],
                        period_index=int(r["period_index"]),
                        billing_date=_parse_date(r["billing_date"]),
                        due_date=_parse_date(r["due_date"]),
                        billed_amount=float(r["billed_amount"]),
                        paid_amount=paid_amt,
                        actual_payment_date=actual_pay_date,
                        recorded_payment_date=recorded_pay_date,
                        days_past_due=dpd,
                        line_utilization=float(r["line_utilization"]),
                    )
                )
            return history

    def get_pending_payments(self, account_id: str, cutoff_date: date) -> List[PendingPaymentDTO]:
        """Consulta pagos en trámite o en compensación a la fecha de corte."""
        cutoff_str = _format_date(cutoff_date)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT payment_id, account_id, amount, payment_date, status
                FROM pending_payments
                WHERE account_id = ? AND payment_date <= ? AND status = 'IN_PROCESS'
                ORDER BY payment_date ASC;
                """,
                (account_id, cutoff_str),
            )
            rows = cursor.fetchall()
            return [
                PendingPaymentDTO(
                    payment_id=r["payment_id"],
                    account_id=r["account_id"],
                    amount=float(r["amount"]),
                    payment_date=_parse_date(r["payment_date"]),
                    status=r["status"],
                )
                for r in rows
            ]

    def save_evaluation(self, evaluation: Dict[str, Any]) -> None:
        """Persiste la evaluación y decisión analítica del agente."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO risk_evaluations (
                    evaluation_id, account_id, evaluation_date, raw_probability,
                    calibrated_probability, risk_band, previous_risk_band,
                    band_change_confirmed, evidence_quality, action_type,
                    rule_applied, explanation, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    evaluation["evaluation_id"],
                    evaluation["account_id"],
                    _format_date(evaluation["evaluation_date"]),
                    float(evaluation["raw_probability"]),
                    float(evaluation["calibrated_probability"]),
                    str(evaluation["risk_band"]),
                    str(evaluation.get("previous_risk_band")) if evaluation.get("previous_risk_band") else None,
                    1 if evaluation.get("band_change_confirmed") else 0,
                    str(evaluation["evidence_quality"]),
                    str(evaluation["action_type"]),
                    str(evaluation["rule_applied"]),
                    str(evaluation["explanation"]),
                    _format_datetime(evaluation.get("created_at")),
                ),
            )
            conn.commit()

    def get_account_notices_count(self, account_id: str, cycle_start_date: date, cutoff_date: date) -> int:
        """Obtiene el número de avisos programados/despachados para la cuenta en el ciclo actual."""
        start_str = _format_date(cycle_start_date)
        cutoff_str = _format_date(cutoff_date)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT COUNT(*) as cnt
                FROM contact_notices
                WHERE account_id = ?
                  AND scheduled_date >= ?
                  AND scheduled_date <= ?
                  AND status IN ('SCHEDULED', 'APPROVED', 'DISPATCHED', 'CAPTURED');
                """,
                (account_id, start_str, cutoff_str),
            )
            row = cursor.fetchone()
            return int(row["cnt"]) if row else 0

    def get_last_notice_date(self, account_id: str) -> Optional[date]:
        """Retorna la fecha del último aviso enviado para verificar la separación mínima."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT MAX(scheduled_date) as last_date
                FROM contact_notices
                WHERE account_id = ?
                  AND status IN ('SCHEDULED', 'APPROVED', 'DISPATCHED', 'CAPTURED');
                """,
                (account_id,),
            )
            row = cursor.fetchone()
            if row and row["last_date"]:
                return _parse_date(row["last_date"])
            return None

    def save_notice(self, notice: Dict[str, Any]) -> None:
        """Registra un aviso programado, aprobado o rechazado."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO contact_notices (
                    notice_id, account_id, evaluation_id, channel,
                    scheduled_date, scheduled_time, tone, subject,
                    body_text, validation_status, status, rejection_reason, sent_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    notice["notice_id"],
                    notice["account_id"],
                    notice.get("evaluation_id"),
                    notice.get("channel", "EMAIL"),
                    _format_date(notice["scheduled_date"]),
                    notice.get("scheduled_time", "10:00:00"),
                    str(notice["tone"]),
                    notice["subject"],
                    notice["body_text"],
                    notice.get("validation_status", "PASSED"),
                    notice.get("status", "SCHEDULED"),
                    notice.get("rejection_reason"),
                    _format_datetime(notice.get("sent_at")) if notice.get("sent_at") else None,
                ),
            )
            conn.commit()

    def update_payment_record(self, account_id: str, payment_date: date, amount: float, actor: str) -> None:
        """
        Permite al analista registrar o corregir un pago desde la cola de revisión.
        Actualiza el saldo de la cuenta, liquida pagos pendientes y registra la pista de auditoría.
        """
        pay_str = _format_date(payment_date)
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 1. Obtener saldo actual
            cursor.execute("SELECT current_balance, status FROM accounts WHERE account_id = ?;", (account_id,))
            account = cursor.fetchone()
            if not account:
                raise ValueError(f"No existe la cuenta con account_id: {account_id}")

            current_balance = float(account["current_balance"])
            new_balance = max(0.0, current_balance - amount)
            new_status = "PAID" if new_balance == 0.0 else "PENDING_PAYMENT"

            cursor.execute(
                """
                UPDATE accounts
                SET current_balance = ?, status = ?
                WHERE account_id = ?;
                """,
                (new_balance, new_status, account_id),
            )

            # 2. Si existía un pago pendiente, marcarlo CLEARED
            cursor.execute(
                """
                UPDATE pending_payments
                SET status = 'CLEARED'
                WHERE account_id = ? AND status = 'IN_PROCESS' AND payment_date <= ?;
                """,
                (account_id, pay_str),
            )

            # 3. Registrar en pista de auditoría inmutable
            log_id = f"LOG-{uuid.uuid4().hex[:12].upper()}"
            payload_json = json.dumps({
                "account_id": account_id,
                "payment_date": pay_str,
                "amount": amount,
                "previous_balance": current_balance,
                "new_balance": new_balance,
                "new_status": new_status,
                "action": "MANUAL_PAYMENT_CORRECTION"
            })
            cursor.execute(
                """
                INSERT INTO audit_logs (log_id, account_id, timestamp, event_type, actor, payload)
                VALUES (?, ?, ?, 'CORRECTION', ?, ?);
                """,
                (log_id, account_id, datetime.now().isoformat(), actor, payload_json),
            )

            conn.commit()

    def get_review_queue(self) -> List[Dict[str, Any]]:
        """Retorna los casos pendientes de revisión humana ordenados por días al vencimiento."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT case_id, account_id, evaluation_id, days_to_due,
                       risk_band, reason, agent_hypothesis, status,
                       corrected_data, resolved_by, resolved_at, created_at
                FROM review_queue
                WHERE status = 'PENDING'
                ORDER BY days_to_due ASC, created_at ASC;
                """
            )
            rows = cursor.fetchall()
            result: List[Dict[str, Any]] = []
            for r in rows:
                c_data = None
                if r["corrected_data"]:
                    try:
                        c_data = json.loads(r["corrected_data"])
                    except Exception:
                        c_data = r["corrected_data"]
                result.append({
                    "case_id": r["case_id"],
                    "account_id": r["account_id"],
                    "evaluation_id": r["evaluation_id"],
                    "days_to_due": int(r["days_to_due"]),
                    "risk_band": r["risk_band"],
                    "reason": r["reason"],
                    "agent_hypothesis": r["agent_hypothesis"],
                    "status": r["status"],
                    "corrected_data": c_data,
                    "resolved_by": r["resolved_by"],
                    "resolved_at": _parse_date(r["resolved_at"]),
                    "created_at": r["created_at"],
                })
            return result

    def resolve_review_case(self, case_id: str, actor: str, resolution_notes: str) -> None:
        """Marca un caso de revisión como resuelto y lo audita."""
        now_str = datetime.now().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT account_id FROM review_queue WHERE case_id = ?;", (case_id,))
            case_row = cursor.fetchone()
            if not case_row:
                raise ValueError(f"Caso de revisión no encontrado: {case_id}")

            account_id = case_row["account_id"]
            cursor.execute(
                """
                UPDATE review_queue
                SET status = 'RESOLVED',
                    resolved_by = ?,
                    resolved_at = ?,
                    corrected_data = json_set(COALESCE(corrected_data, '{}'), '$.notes', ?)
                WHERE case_id = ?;
                """,
                (actor, now_str, resolution_notes, case_id),
            )

            # Registrar en auditoría
            log_id = f"LOG-{uuid.uuid4().hex[:12].upper()}"
            payload = json.dumps({
                "case_id": case_id,
                "notes": resolution_notes,
                "status": "RESOLVED"
            })
            cursor.execute(
                """
                INSERT INTO audit_logs (log_id, account_id, timestamp, event_type, actor, payload)
                VALUES (?, ?, ?, 'REVIEW_RESOLVED', ?, ?);
                """,
                (log_id, account_id, now_str, actor, payload),
            )
            conn.commit()

    # =========================================================================
    # Métodos Auxiliares de Persistencia y Consulta para Apoyo a Otros Módulos
    # =========================================================================

    def save_customer(self, customer: Union[Dict[str, Any], CustomerDTO]) -> None:
        """Inserta o actualiza un cliente."""
        c = customer if isinstance(customer, dict) else customer.model_dump()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO customers (customer_id, full_name, email, contact_enabled, created_at)
                VALUES (?, ?, ?, ?, ?);
                """,
                (
                    c["customer_id"],
                    c["full_name"],
                    c["email"],
                    1 if c.get("contact_enabled", True) else 0,
                    _format_date(c.get("created_at", date.today())),
                ),
            )
            conn.commit()

    def save_account(self, account: Union[Dict[str, Any], AccountDTO]) -> None:
        """Inserta o actualiza una cuenta."""
        a = account if isinstance(account, dict) else account.model_dump()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO accounts (
                    account_id, customer_id, credit_limit, current_balance,
                    minimum_payment, due_date, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    a["account_id"],
                    a["customer_id"],
                    float(a["credit_limit"]),
                    float(a["current_balance"]),
                    float(a["minimum_payment"]),
                    _format_date(a["due_date"]),
                    str(a.get("status", "UP_TO_DATE")),
                ),
            )
            conn.commit()

    def save_period_record(self, record: Union[Dict[str, Any], PeriodRecordDTO]) -> None:
        """Inserta o actualiza un registro histórico de período."""
        r = record if isinstance(record, dict) else record.model_dump()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO period_records (
                    record_id, account_id, period_index, billing_date, due_date,
                    billed_amount, paid_amount, actual_payment_date,
                    recorded_payment_date, days_past_due, line_utilization
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    r["record_id"],
                    r["account_id"],
                    int(r["period_index"]),
                    _format_date(r["billing_date"]),
                    _format_date(r["due_date"]),
                    float(r["billed_amount"]),
                    float(r["paid_amount"]),
                    _format_date(r.get("actual_payment_date")),
                    _format_date(r.get("recorded_payment_date")),
                    int(r["days_past_due"]),
                    float(r["line_utilization"]),
                ),
            )
            conn.commit()

    def save_pending_payment(self, payment: Union[Dict[str, Any], PendingPaymentDTO]) -> None:
        """Inserta o actualiza un pago pendiente."""
        p = payment if isinstance(payment, dict) else payment.model_dump()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO pending_payments (payment_id, account_id, amount, payment_date, status)
                VALUES (?, ?, ?, ?, ?);
                """,
                (
                    p["payment_id"],
                    p["account_id"],
                    float(p["amount"]),
                    _format_date(p["payment_date"]),
                    p.get("status", "IN_PROCESS"),
                ),
            )
            conn.commit()

    def save_review_case(self, case: Dict[str, Any]) -> None:
        """Inserta o actualiza un caso en la cola de revisión."""
        c_data = case.get("corrected_data")
        if isinstance(c_data, dict):
            c_data = json.dumps(c_data)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO review_queue (
                    case_id, account_id, evaluation_id, days_to_due, risk_band,
                    reason, agent_hypothesis, status, corrected_data,
                    resolved_by, resolved_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    case["case_id"],
                    case["account_id"],
                    case.get("evaluation_id"),
                    int(case["days_to_due"]),
                    str(case["risk_band"]),
                    case["reason"],
                    case["agent_hypothesis"],
                    case.get("status", "PENDING"),
                    c_data,
                    case.get("resolved_by"),
                    _format_datetime(case.get("resolved_at")) if case.get("resolved_at") else None,
                    _format_datetime(case.get("created_at")),
                ),
            )
            conn.commit()

    def save_audit_log(self, entry: Dict[str, Any]) -> None:
        """Inserta un registro en la pista de auditoría inmutable."""
        payload = entry["payload"]
        if isinstance(payload, dict):
            payload = json.dumps(payload)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO audit_logs (log_id, account_id, timestamp, event_type, actor, payload)
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                (
                    entry["log_id"],
                    entry["account_id"],
                    _format_datetime(entry.get("timestamp")),
                    entry["event_type"],
                    entry["actor"],
                    payload,
                ),
            )
            conn.commit()

    def get_audit_logs(self, account_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Recupera entradas de la pista de auditoría."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if account_id:
                cursor.execute(
                    """
                    SELECT log_id, account_id, timestamp, event_type, actor, payload
                    FROM audit_logs
                    WHERE account_id = ?
                    ORDER BY timestamp DESC;
                    """,
                    (account_id,),
                )
            else:
                cursor.execute(
                    """
                    SELECT log_id, account_id, timestamp, event_type, actor, payload
                    FROM audit_logs
                    ORDER BY timestamp DESC;
                    """
                )
            rows = cursor.fetchall()
            logs = []
            for r in rows:
                p = r["payload"]
                try:
                    p = json.loads(p)
                except Exception:
                    pass
                logs.append({
                    "log_id": r["log_id"],
                    "account_id": r["account_id"],
                    "timestamp": r["timestamp"],
                    "event_type": r["event_type"],
                    "actor": r["actor"],
                    "payload": p,
                })
            return logs

    def save_captured_email(self, email_data: Dict[str, Any]) -> None:
        """Guarda un correo capturado físicamente en el servidor SMTP local."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO captured_emails (email_id, sender, recipient, subject, raw_content, captured_at)
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                (
                    email_data["email_id"],
                    email_data["sender"],
                    email_data["recipient"],
                    email_data["subject"],
                    email_data["raw_content"],
                    _format_datetime(email_data.get("captured_at")),
                ),
            )
            conn.commit()

    def get_captured_emails(self) -> List[Dict[str, Any]]:
        """Retorna todos los correos capturados en la bandeja SMTP local."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT email_id, sender, recipient, subject, raw_content, captured_at
                FROM captured_emails
                ORDER BY captured_at DESC;
                """
            )
            return [dict(r) for r in cursor.fetchall()]

    def get_account(self, account_id: str) -> Optional[AccountDTO]:
        """Obtiene una cuenta individual por su identificador."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT account_id, customer_id, credit_limit, current_balance,
                       minimum_payment, due_date, status
                FROM accounts
                WHERE account_id = ?;
                """,
                (account_id,),
            )
            r = cursor.fetchone()
            if not r:
                return None
            return AccountDTO(
                account_id=r["account_id"],
                customer_id=r["customer_id"],
                credit_limit=float(r["credit_limit"]),
                current_balance=float(r["current_balance"]),
                minimum_payment=float(r["minimum_payment"]),
                due_date=_parse_date(r["due_date"]),
                status=r["status"],
            )

    def get_notices(self, account_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Obtiene avisos programados/despachados."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if account_id:
                cursor.execute(
                    "SELECT * FROM contact_notices WHERE account_id = ? ORDER BY scheduled_date ASC;",
                    (account_id,),
                )
            else:
                cursor.execute("SELECT * FROM contact_notices ORDER BY scheduled_date ASC;")
            return [dict(r) for r in cursor.fetchall()]
