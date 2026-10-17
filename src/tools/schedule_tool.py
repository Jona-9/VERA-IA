"""
ScheduleNoticeTool: herramienta de acción con límites deterministas duros
(RF-11, Principio Constitucional II).

Todas las reglas de buen trato y de seguridad residen en código ejecutado
aquí, no en el criterio del LLM orquestador: si una precondición de política
no se cumple, la herramienta rechaza la solicitud con un código tipificado en
vez de "persuadir" o reintentar. Ver contrato formal en
`sdd/specs/001-early-collection-agent/contracts/tools_contract.md`.

Esta herramienta solo depende de los métodos de `PortfolioRepository`
descritos en `sdd/specs/001-early-collection-agent/contracts/repository_contract.md`
(duck typing vía `PolicyRepositoryPort`), por lo que no bloquea su desarrollo
ni sus pruebas a la implementación concreta de SQLite del Integrante 1.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import List, Optional, Protocol

from pydantic import BaseModel, Field

from src.domain.entities import NoticeStatus, RiskBand, Tone
from src.policy.config import ContactWindowConfig, PolicyConfig
from src.policy.engine import get_contact_window


# ---------------------------------------------------------------------------
# Códigos de rechazo tipificados (tools_contract.md, sección 1)
# ---------------------------------------------------------------------------

ERR_ALREADY_PAID = "ERR_ALREADY_PAID"
ERR_PAYMENT_IN_PROGRESS = "ERR_PAYMENT_IN_PROGRESS"
ERR_OUTSIDE_WINDOW = "ERR_OUTSIDE_WINDOW"
ERR_MAX_NOTICES_EXCEEDED = "ERR_MAX_NOTICES_EXCEEDED"
ERR_MIN_SEPARATION_VIOLATED = "ERR_MIN_SEPARATION_VIOLATED"
ERR_INVALID_TONE_FOR_BAND = "ERR_INVALID_TONE_FOR_BAND"
ERR_UNKNOWN_ACCOUNT = "ERR_UNKNOWN_ACCOUNT"


# ---------------------------------------------------------------------------
# Esquema de entrada / salida (tools_contract.md, sección 1)
# ---------------------------------------------------------------------------


class ScheduleNoticeInput(BaseModel):
    account_id: str = Field(description="Identificador de la cuenta u obligación")
    evaluation_id: str = Field(description="Identificador de la evaluación que justifica el aviso")
    risk_band: RiskBand = Field(description="Banda de riesgo estimada")
    scheduled_date: date = Field(description="Fecha propuesta para el envío dentro de la ventana")
    tone: Tone = Field(description="Tono autorizado")
    subject: str = Field(description="Asunto del correo redactado")
    body_text: str = Field(description="Cuerpo del mensaje validado previamente por ToneGuard")


class ScheduleNoticeOutput(BaseModel):
    success: bool
    notice_id: Optional[str] = None
    status: str  # 'APPROVED' | 'REJECTED'
    rejection_code: Optional[str] = None
    message: str


# ---------------------------------------------------------------------------
# Puerto mínimo de repositorio requerido (subconjunto de PortfolioRepository)
# ---------------------------------------------------------------------------


class _AccountLike(Protocol):
    account_id: str
    current_balance: float
    status: str
    due_date: date


class _PendingPaymentLike(Protocol):
    payment_id: str
    amount: float
    payment_date: date
    status: str


class PolicyRepositoryPort(Protocol):
    """
    Subconjunto de `PortfolioRepository` (ver repository_contract.md) que
    `ScheduleNoticeTool` necesita. Cualquier objeto que implemente estos
    métodos con esta firma (p. ej. `SQLitePortfolioRepository` de Dev 1, o un
    mock en los tests) sirve como repositorio aquí, sin necesidad de heredar
    de ninguna clase concreta.
    """

    def get_portfolio_accounts(self, cutoff_date: date) -> List[_AccountLike]: ...

    def get_pending_payments(self, account_id: str, cutoff_date: date) -> List[_PendingPaymentLike]: ...

    def get_account_notices_count(self, account_id: str, cycle_start_date: date, cutoff_date: date) -> int: ...

    def get_last_notice_date(self, account_id: str) -> Optional[date]: ...

    def save_notice(self, notice: dict) -> None: ...


class ScheduleNoticeTool:
    """
    Valida las precondiciones duras de política y, si todas se cumplen,
    registra el aviso vía `repository.save_notice(...)`.

    El orden de validación sigue exactamente `tools_contract.md` (1 a 6):
    pago ya realizado -> pago en trámite -> ventana autorizada -> cuota
    máxima de avisos -> separación mínima -> tono permitido para la banda.
    La primera regla violada determina el código de rechazo devuelto; no se
    acumulan errores.
    """

    def __init__(self, policy: PolicyConfig, repository: PolicyRepositoryPort):
        self._policy = policy
        self._repo = repository

    def run(self, input_data: ScheduleNoticeInput) -> ScheduleNoticeOutput:
        account = self._find_account(input_data.account_id, input_data.scheduled_date)
        if account is None:
            return self._rejected(
                ERR_UNKNOWN_ACCOUNT,
                f"No se encontró la cuenta {input_data.account_id} a la fecha {input_data.scheduled_date}.",
            )

        # 1. Regla de no contacto si ya pagó.
        if account.current_balance <= 0 or account.status == "PAID":
            return self._rejected(
                ERR_ALREADY_PAID,
                f"La cuenta {account.account_id} ya está pagada (saldo={account.current_balance}); no se contacta.",
            )

        # 2. Regla de pago en trámite.
        pending_payments = self._repo.get_pending_payments(input_data.account_id, input_data.scheduled_date)
        if any(payment.status == "IN_PROCESS" for payment in pending_payments):
            return self._rejected(
                ERR_PAYMENT_IN_PROGRESS,
                f"La cuenta {account.account_id} tiene al menos un pago en proceso ('IN_PROCESS'); no se contacta.",
            )

        # 3. Regla de ventana autorizada.
        is_preventive = input_data.scheduled_date < account.due_date
        window = get_contact_window(input_data.risk_band, is_preventive, self._policy)
        window_error = self._check_window(input_data, account.due_date, window, is_preventive)
        if window_error is not None:
            return self._rejected(ERR_OUTSIDE_WINDOW, window_error)

        # 4. Regla de máximo de avisos del ciclo.
        cycle_start_date = self._cycle_start_date(account.due_date, input_data.risk_band, self._policy)
        notices_count = self._repo.get_account_notices_count(
            input_data.account_id, cycle_start_date, input_data.scheduled_date
        )
        if notices_count >= window.max_notices:
            return self._rejected(
                ERR_MAX_NOTICES_EXCEEDED,
                f"Ya se despacharon {notices_count} avisos en el ciclo actual "
                f"(máximo permitido para {input_data.risk_band.value}: {window.max_notices}).",
            )

        # 5. Regla de separación mínima.
        last_notice_date = self._repo.get_last_notice_date(input_data.account_id)
        if last_notice_date is not None:
            separation_days = (input_data.scheduled_date - last_notice_date).days
            if separation_days < window.min_separation_days:
                return self._rejected(
                    ERR_MIN_SEPARATION_VIOLATED,
                    f"Último aviso enviado el {last_notice_date}; se requieren al menos "
                    f"{window.min_separation_days} días de separación (hay {separation_days}).",
                )

        # 6. Regla de restricción de tono por banda/fase.
        tone_error = self._check_tone(input_data, account.due_date, window)
        if tone_error is not None:
            return self._rejected(ERR_INVALID_TONE_FOR_BAND, tone_error)

        notice_id = str(uuid.uuid4())
        self._repo.save_notice(
            {
                "notice_id": notice_id,
                "account_id": input_data.account_id,
                "evaluation_id": input_data.evaluation_id,
                "channel": "EMAIL",
                "scheduled_date": input_data.scheduled_date,
                "tone": input_data.tone.value,
                "subject": input_data.subject,
                "body_text": input_data.body_text,
                "status": NoticeStatus.APPROVED.value,
            }
        )
        return ScheduleNoticeOutput(
            success=True,
            notice_id=notice_id,
            status="APPROVED",
            rejection_code=None,
            message=f"Aviso {notice_id} aprobado y programado para {input_data.scheduled_date}.",
        )

    # -- helpers -----------------------------------------------------------

    def _find_account(self, account_id: str, cutoff_date: date) -> Optional[_AccountLike]:
        for account in self._repo.get_portfolio_accounts(cutoff_date):
            if account.account_id == account_id:
                return account
        return None

    @staticmethod
    def _check_window(
        input_data: ScheduleNoticeInput,
        due_date: date,
        window: ContactWindowConfig,
        is_preventive: bool,
    ) -> Optional[str]:
        if not window.allowed:
            phase = "preventivo" if is_preventive else "post-vencimiento"
            return f"El contacto {phase} no está permitido para la banda {input_data.risk_band.value}."

        if is_preventive:
            days_before_due = (due_date - input_data.scheduled_date).days
            if days_before_due not in window.window_days_before_due:
                return (
                    f"La fecha {input_data.scheduled_date} está a {days_before_due} días antes del vencimiento "
                    f"({due_date}); fuera de la ventana permitida {window.window_days_before_due} "
                    f"para {input_data.risk_band.value}."
                )
        else:
            days_after_due = (input_data.scheduled_date - due_date).days
            if days_after_due <= 0 or days_after_due not in window.window_days_after_due:
                return (
                    f"La fecha {input_data.scheduled_date} está a {days_after_due} días después del vencimiento "
                    f"({due_date}); fuera de la ventana permitida {window.window_days_after_due} "
                    f"para {input_data.risk_band.value}."
                )
        return None

    @staticmethod
    def _check_tone(
        input_data: ScheduleNoticeInput, due_date: date, window: ContactWindowConfig
    ) -> Optional[str]:
        if input_data.tone not in window.allowed_tones:
            return (
                f"El tono '{input_data.tone.value}' no está permitido para la banda "
                f"{input_data.risk_band.value} en esta fase (tonos permitidos: "
                f"{[t.value for t in window.allowed_tones]})."
            )
        # Restricción explícita del contrato: FIRM solo aplica post-vencimiento
        # y únicamente para bandas ALTA o CRITICA.
        if input_data.tone == Tone.FIRM:
            if input_data.scheduled_date <= due_date or input_data.risk_band not in (
                RiskBand.ALTA,
                RiskBand.CRITICA,
            ):
                return (
                    "El tono 'FIRM' solo puede usarse después del vencimiento y únicamente "
                    "para las bandas ALTA o CRITICA."
                )
        return None

    @staticmethod
    def _cycle_start_date(due_date: date, risk_band: RiskBand, policy: PolicyConfig) -> date:
        """
        Fecha de inicio del ciclo de contacto vigente para el conteo de cuota
        de avisos (`get_account_notices_count`).

        ASUNCIÓN DE DISEÑO: el modelo de dominio compartido no define una
        entidad explícita de "ciclo de facturación", así que se delimita el
        ciclo como la ventana de contacto declarada por la banda alrededor de
        `due_date`: desde el día más lejano de la ventana preventiva hasta
        `due_date` inclusive. Esto evita que avisos de ciclos anteriores
        cuenten contra la cuota del ciclo actual.
        """
        band_policy = policy.bands[risk_band]
        max_days_before = max(band_policy.preventive_contact.window_days_before_due, default=0)
        return due_date - timedelta(days=max_days_before)

    @staticmethod
    def _rejected(code: str, message: str) -> ScheduleNoticeOutput:
        return ScheduleNoticeOutput(success=False, notice_id=None, status="REJECTED", rejection_code=code, message=message)
