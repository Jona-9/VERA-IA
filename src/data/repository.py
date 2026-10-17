"""
Definición de contratos DTO y protocolo abstracto PortfolioRepository.
Cumple con la especificación sdd/specs/001-early-collection-agent/contracts/repository_contract.md
"""

from datetime import date
from typing import Protocol, List, Optional, Dict, Any, runtime_checkable
from pydantic import BaseModel


class CustomerDTO(BaseModel):
    customer_id: str
    full_name: str
    email: str
    contact_enabled: bool
    created_at: Optional[date] = None


class AccountDTO(BaseModel):
    account_id: str
    customer_id: str
    credit_limit: float
    current_balance: float
    minimum_payment: float
    due_date: date
    status: str


class PeriodRecordDTO(BaseModel):
    record_id: str
    account_id: str
    period_index: int
    billing_date: date
    due_date: date
    billed_amount: float
    paid_amount: float
    actual_payment_date: Optional[date] = None
    recorded_payment_date: Optional[date] = None
    days_past_due: int
    line_utilization: float


class PendingPaymentDTO(BaseModel):
    payment_id: str
    account_id: str
    amount: float
    payment_date: date
    status: str  # 'IN_PROCESS', 'CLEARED', 'REJECTED'


@runtime_checkable
class PortfolioRepository(Protocol):
    """
    Protocolo abstracto para el acceso a datos de cartera y gestión de eventos.
    Desacopla la lógica de negocio y agentes del motor de base de datos subyacente.
    """

    def get_portfolio_accounts(self, cutoff_date: date) -> List[AccountDTO]:
        """Obtiene todas las cuentas activas para ser evaluadas a la fecha de corte."""
        ...

    def get_customer(self, customer_id: str) -> Optional[CustomerDTO]:
        """Obtiene los datos de contacto y consentimiento del cliente."""
        ...

    def get_period_history(self, account_id: str, cutoff_date: date) -> List[PeriodRecordDTO]:
        """
        Obtiene el historial cronológico de períodos cerrado estrictamente a la fecha de corte.
        PROHIBIDO retornar datos con billing_date o registro posterior a cutoff_date (Principio IV).
        """
        ...

    def get_pending_payments(self, account_id: str, cutoff_date: date) -> List[PendingPaymentDTO]:
        """Consulta pagos en trámite o en proceso de compensación a la fecha de corte."""
        ...

    def save_evaluation(self, evaluation: Dict[str, Any]) -> None:
        """Persiste la evaluación y decisión analítica del agente."""
        ...

    def get_account_notices_count(self, account_id: str, cycle_start_date: date, cutoff_date: date) -> int:
        """Obtiene el número de avisos ya despachados para la cuenta en el ciclo actual."""
        ...

    def get_last_notice_date(self, account_id: str) -> Optional[date]:
        """Retorna la fecha del último aviso enviado para verificar la separación mínima."""
        ...

    def save_notice(self, notice: Dict[str, Any]) -> None:
        """Registra un aviso programado o enviado."""
        ...

    def update_payment_record(self, account_id: str, payment_date: date, amount: float, actor: str) -> None:
        """Permite al analista registrar o corregir un pago desde la cola de revisión."""
        ...

    def get_review_queue(self) -> List[Dict[str, Any]]:
        """Retorna los casos pendientes de revisión humana ordenados por días al vencimiento."""
        ...

    def resolve_review_case(self, case_id: str, actor: str, resolution_notes: str) -> None:
        """Marca un caso de revisión como resuelto."""
        ...
