"""
Modelos de dominio y contratos de datos para VERAIA.
Define todas las entidades, enumeraciones y tipos de datos compartidos.
"""

from datetime import date, datetime
from enum import Enum
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class RiskBand(str, Enum):
    BAJA = "BAJA"
    MODERADA = "MODERADA"
    ALTA = "ALTA"
    CRITICA = "CRITICA"


class Tone(str, Enum):
    NEUTRAL = "NEUTRAL"
    PREVENTIVE = "PREVENTIVE"
    FIRM = "FIRM"


class EvidenceQuality(str, Enum):
    SUFFICIENT = "SUFFICIENT"
    INSUFFICIENT = "INSUFFICIENT"
    INCONSISTENT = "INCONSISTENT"


class ActionType(str, Enum):
    NO_ACTION = "NO_ACTION"
    SCHEDULE_NOTICE = "SCHEDULE_NOTICE"
    INVESTIGATE = "INVESTIGATE"
    ESCALATE_HUMAN = "ESCALATE_HUMAN"


class NoticeStatus(str, Enum):
    SCHEDULED = "SCHEDULED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    DISPATCHED = "DISPATCHED"
    CAPTURED = "CAPTURED"


class AccountStatus(str, Enum):
    UP_TO_DATE = "UP_TO_DATE"
    PENDING_PAYMENT = "PENDING_PAYMENT"
    PAID = "PAID"
    OVERDUE = "OVERDUE"


class Customer(BaseModel):
    """Representa al titular de una obligación financiera."""
    customer_id: str = Field(description="Identificador único anonimizado")
    full_name: str = Field(description="Nombre para inyección local en plantilla")
    email: str = Field(description="Dirección de correo electrónico de contacto")
    contact_enabled: bool = Field(default=True, description="Consentimiento de contacto activo")
    created_at: date = Field(description="Fecha de alta del cliente")


class Account(BaseModel):
    """Representa la cuenta de crédito o préstamo monitoreada."""
    account_id: str = Field(description="Identificador único de la cuenta u obligación")
    customer_id: str = Field(description="Identificador del cliente titular")
    credit_limit: float = Field(ge=0, description="Límite total asignado de la línea")
    current_balance: float = Field(ge=0, description="Saldo total adeudado a la fecha de corte")
    minimum_payment: float = Field(ge=0, description="Pago mínimo exigible en el período")
    due_date: date = Field(description="Fecha pactada de vencimiento de la cuota corriente")
    status: AccountStatus = Field(default=AccountStatus.UP_TO_DATE, description="Estado actual de pago")


class PeriodRecord(BaseModel):
    """Registro histórico de comportamiento mensual de una cuenta."""
    record_id: str = Field(description="Identificador único del registro histórico")
    account_id: str = Field(description="Cuenta referenciada")
    period_index: int = Field(description="Índice secuencial relativo del período (0, 1, 2, ...)")
    billing_date: date = Field(description="Fecha de facturación / corte del período")
    due_date: date = Field(description="Fecha límite pactada para pago")
    billed_amount: float = Field(ge=0, description="Monto total facturado")
    paid_amount: float = Field(ge=0, description="Monto efectivamente pagado")
    actual_payment_date: Optional[date] = Field(default=None, description="Fecha real en que el cliente pagó")
    recorded_payment_date: Optional[date] = Field(default=None, description="Fecha administrativa de registro bancario")
    days_past_due: int = Field(ge=0, description="Días de atraso calculados a la fecha real de pago o corte")
    line_utilization: float = Field(ge=0, description="Ratio saldo / límite al cierre del período")


class PendingPayment(BaseModel):
    """Pago en trámite o en proceso de compensación interbancaria."""
    payment_id: str = Field(description="Identificador de la transacción")
    account_id: str = Field(description="Cuenta referenciada")
    amount: float = Field(gt=0, description="Monto abonado")
    payment_date: date = Field(description="Fecha de emisión del pago")
    status: str = Field(default="IN_PROCESS", description="'IN_PROCESS', 'CLEARED', 'REJECTED'")


class SignalSet(BaseModel):
    """Conjunto de señales cuantitativas calculadas a fecha de corte sin mirar el futuro."""
    account_id: str = Field(description="Cuenta evaluada")
    cutoff_date: date = Field(description="Fecha de corte en que se evalúa la cartera")
    credit_utilization_ratio: float = Field(description="Utilización actual de la línea (saldo / límite)")
    consecutive_min_payments: int = Field(ge=0, description="Meses consecutivos pagando solo el mínimo")
    payment_to_billed_ratio: float = Field(description="Monto pagado respecto a lo facturado en el último período")
    payment_ratio_drop: float = Field(description="Caída porcentual del ratio de pago frente a la historia reciente")
    historical_delinquency_rate: float = Field(description="Proporción de períodos con atraso >= 1 día")
    max_past_due_days: int = Field(ge=0, description="Máximo de días de mora registrados en el historial")
    delinquency_trend: float = Field(description="Tendencia o variación reciente en días de atraso")


class RiskEvaluation(BaseModel):
    """Juicio y decisión analítica generada para una cuenta en un ciclo."""
    evaluation_id: str = Field(description="Identificador único de la evaluación")
    account_id: str = Field(description="Cuenta evaluada")
    evaluation_date: date = Field(description="Fecha del ciclo diario de evaluación")
    raw_probability: float = Field(ge=0, le=1, description="Probabilidad base estimada por Regresión Logística")
    calibrated_probability: float = Field(ge=0, le=1, description="Probabilidad calibrada tras Platt scaling")
    risk_band: RiskBand = Field(description="Banda asignada (BAJA, MODERADA, ALTA, CRITICA)")
    previous_risk_band: Optional[RiskBand] = Field(default=None, description="Banda del ciclo anterior para histéresis")
    band_change_confirmed: bool = Field(default=False, description="Superó margen 0.05 o 2 ciclos consecutivos")
    evidence_quality: EvidenceQuality = Field(description="Calidad de la evidencia observada")
    action_type: ActionType = Field(description="Acción determinada por política")
    rule_applied: str = Field(description="Código o regla de negocio aplicada")
    explanation: str = Field(description="Explicación auditable de la decisión")


class ContactNotice(BaseModel):
    """Aviso de cobranza preparado para despacho."""
    notice_id: str = Field(description="Identificador del aviso")
    account_id: str = Field(description="Cuenta asociada")
    evaluation_id: str = Field(description="Evaluación origen")
    channel: str = Field(default="EMAIL", description="Canal de contacto (exclusivamente 'EMAIL')")
    scheduled_date: date = Field(description="Fecha de envío autorizada")
    scheduled_time: str = Field(default="10:00:00", description="Hora prevista de despacho")
    tone: Tone = Field(description="Tono autorizado")
    subject: str = Field(description="Asunto del correo")
    body_text: str = Field(description="Cuerpo validado por ToneGuard")
    validation_status: str = Field(default="PASSED", description="'PASSED' o 'FAILED_FALLBACK_APPLIED'")
    status: NoticeStatus = Field(default=NoticeStatus.SCHEDULED, description="Estado del aviso")
    rejection_reason: Optional[str] = Field(default=None, description="Motivo si fue rechazado por la herramienta")


class ReviewCase(BaseModel):
    """Caso derivado para supervisión o corrección humana."""
    case_id: str = Field(description="Identificador del caso en cola")
    account_id: str = Field(description="Cuenta en revisión")
    evaluation_id: str = Field(description="Evaluación asociada")
    days_to_due: int = Field(description="Días para el vencimiento (criterio de prioridad)")
    risk_band: RiskBand = Field(description="Banda asignada")
    reason: str = Field(description="Motivo de derivación")
    agent_hypothesis: str = Field(description="Hipótesis formulada por el agente")
    status: str = Field(default="PENDING", description="'PENDING', 'RESOLVED', 'DISMISSED'")
    corrected_data: Optional[Dict[str, Any]] = Field(default=None, description="Corrección ingresada por el analista")
    resolved_by: Optional[str] = Field(default=None, description="Identificador del analista")
    resolved_at: Optional[datetime] = Field(default=None, description="Marca temporal de resolución")


class CapturedEmail(BaseModel):
    """Correo capturado físicamente en el servidor SMTP local de prueba."""
    email_id: str = Field(description="Identificador único del mensaje recibido")
    sender: str = Field(description="Remitente")
    recipient: str = Field(description="Destinatario")
    subject: str = Field(description="Asunto")
    raw_content: str = Field(description="Mensaje RFC 822 completo con cabeceras")
    captured_at: datetime = Field(description="Fecha y hora de captura en el socket")


class AuditLogEntry(BaseModel):
    """Registro inmutable de trazabilidad y auditoría de eventos."""
    log_id: str = Field(description="Identificador secuencial del log")
    account_id: str = Field(description="Cuenta referenciada")
    timestamp: datetime = Field(description="Momento exacto del evento")
    event_type: str = Field(description="'EVALUATION', 'TOOL_CHECK', 'TOOL_REJECTION', 'CORRECTION', 'DISPATCH'")
    actor: str = Field(description="'AGENT', 'TOOL_GUARD', 'ANALYST', 'SUPERVISOR'")
    payload: Dict[str, Any] = Field(description="Variables observadas, reglas ejecutadas y resultado")
