"""
Orquestador del ciclo diario de cobranza temprana (RF-07, RF-12; T017/T018).

Cada día simulado tiene dos momentos:

- Corte de revisión (09:00): `run_evaluation` evalúa toda la cartera con datos hasta la fecha
  de corte, deriva a revisión humana lo dudoso y deja los avisos permitidos por la política en
  estado APPROVED. Solo `ScheduleNoticeTool` puede aprobar un aviso (Principio II).
- Despacho (10:00): `close_review_and_dispatch` envía únicamente los avisos APPROVED cuya
  cuenta no tiene casos de revisión pendientes. Lo que no se revisó a tiempo no sale hoy.

El orquestador no decide por sí mismo qué es permitido: delega en `src/policy/engine.py` y en
`ScheduleNoticeTool`, y deja una entrada de auditoría por cada evaluación, rechazo y despacho.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Protocol

from src.agent.drafter import DraftContext, MessageDrafter, compose_notice_message, format_due_date
from src.agent.investigator import (
    ACTION_ESCALATE_HUMAN,
    ACTION_WAIT_FOR_CLEARING,
    InconsistencyInvestigator,
    InvestigationContext,
    build_investigator,
)
from src.analytics.model import RiskModel
from src.analytics.signals import compute_signals_for_account
from src.data.repository import AccountDTO
from src.data.sqlite_repo import SQLitePortfolioRepository
from src.domain.audit import create_audit_entry
from src.domain.entities import (
    Account,
    ActionType,
    EvidenceQuality,
    NoticeStatus,
    PeriodRecord,
    RiskBand,
    SignalSet,
    Tone,
)
from src.mail.client import SMTPMailClient, build_mail_client
from src.policy.config import PolicyConfig
from src.policy.engine import (
    apply_hysteresis,
    assess_evidence_quality,
    classify_risk_band,
    get_contact_window,
)
from src.tools.schedule_tool import ScheduleNoticeInput, ScheduleNoticeTool

ACTIVE_NOTICE_STATUSES = (
    NoticeStatus.SCHEDULED.value,
    NoticeStatus.APPROVED.value,
    NoticeStatus.DISPATCHED.value,
    NoticeStatus.CAPTURED.value,
)

REASON_UNEXPLAINED_PAYMENT = "UNEXPLAINED_PAYMENT"
REASON_PAYMENT_IN_PROCESS = "PAYMENT_IN_PROCESS"
REASON_OVER_LIMIT = "OVER_LIMIT"
REASON_NOTICES_EXHAUSTED = "NOTICES_EXHAUSTED"

REVIEW_REASON_TEXT = {
    REASON_UNEXPLAINED_PAYMENT: "Pago reportado que no cuadra con lo facturado.",
    REASON_PAYMENT_IN_PROCESS: "Pago en proceso. Confirmar acreditación.",
    REASON_OVER_LIMIT: "Saldo sobre el límite. Confirmar cupo.",
    REASON_NOTICES_EXHAUSTED: "Avisos agotados sin pago. Le escribes tú.",
}


class SendDaySelector(Protocol):
    """Elige el día de envío preventivo dentro de la ventana que autoriza la política."""

    def choose(self, account_id: str, band: RiskBand, window_days: List[int]) -> int: ...


class EarliestDaySelector:
    """Selector por defecto: el primer día disponible de la ventana (sin exploración)."""

    def choose(self, account_id: str, band: RiskBand, window_days: List[int]) -> int:
        return max(window_days)


class NoticeDispatcher(Protocol):
    def send(self, notice: Dict[str, Any], recipient: str) -> str:
        """Envía el aviso y retorna el estado resultante ('DISPATCHED' o 'CAPTURED')."""
        ...


class NullDispatcher:
    """Despacho en seco para simulaciones sin servidor SMTP (benchmark)."""

    def send(self, notice: Dict[str, Any], recipient: str) -> str:
        return NoticeStatus.DISPATCHED.value


class SmtpNoticeDispatcher:
    """Despacha vía smtplib (captura local por defecto, SMTP real con VERAIA_MAIL_MODE=real)."""

    def __init__(self, repo: SQLitePortfolioRepository, client: Optional[SMTPMailClient] = None,
                 confirm_timeout: float = 2.0):
        self._repo = repo
        self._client = client or build_mail_client()
        self._confirm_timeout = confirm_timeout

    def send(self, notice: Dict[str, Any], recipient: str) -> str:
        notice_id = notice["notice_id"]
        self._client.send(
            recipient=recipient,
            subject=notice["subject"],
            body_text=notice["body_text"],
            extra_headers={"X-VERAIA-Notice-Id": notice_id},
        )
        if not self._client.settings.is_local:
            # Envío real: no hay bandeja de captura que confirmar; el SMTP aceptó el mensaje.
            return NoticeStatus.DISPATCHED.value
        deadline = time.monotonic() + self._confirm_timeout
        while time.monotonic() < deadline:
            if any(notice_id in e["raw_content"] for e in self._repo.get_captured_emails()):
                return NoticeStatus.CAPTURED.value
            time.sleep(0.05)
        return NoticeStatus.DISPATCHED.value


@dataclass
class AccountDecision:
    account_id: str
    customer_name: str
    evaluation: Dict[str, Any]
    signals: SignalSet
    days_to_due: int
    action: ActionType
    rule: str
    detail: str
    notice_id: Optional[str] = None
    rejection_code: Optional[str] = None
    review_case_id: Optional[str] = None


@dataclass
class CycleReport:
    cycle_date: date
    decisions: List[AccountDecision] = field(default_factory=list)
    elapsed_seconds: float = 0.0

    def count(self, action: ActionType) -> int:
        return sum(1 for d in self.decisions if d.action == action)

    @property
    def notices_approved(self) -> int:
        return sum(1 for d in self.decisions if d.notice_id)

    @property
    def tool_rejections(self) -> int:
        return sum(1 for d in self.decisions if d.rejection_code)


@dataclass
class DispatchReport:
    cycle_date: date
    sent: List[str] = field(default_factory=list)
    held: Dict[str, str] = field(default_factory=dict)  # notice_id -> motivo


def _unwrap(value: Any) -> str:
    return value.value if hasattr(value, "value") else str(value)


class DailyCycleOrchestrator:
    """Evalúa la cartera, programa avisos mediante la herramienta y despacha a las 10:00."""

    def __init__(
        self,
        repo: SQLitePortfolioRepository,
        model: RiskModel,
        policy: PolicyConfig,
        selector: Optional[SendDaySelector] = None,
        drafter: Optional[MessageDrafter] = None,
        investigator: Optional[InconsistencyInvestigator] = None,
    ):
        self.repo = repo
        self.model = model
        self.policy = policy
        self.selector = selector or EarliestDaySelector()
        self.drafter = drafter
        self.investigator = investigator or build_investigator()
        self.tool = ScheduleNoticeTool(policy, repo)

    # ------------------------------------------------------------------
    # Corte de revisión (09:00)
    # ------------------------------------------------------------------

    def run_evaluation(self, cycle_date: date) -> CycleReport:
        started = time.perf_counter()
        report = CycleReport(cycle_date=cycle_date)
        for account in self.repo.get_portfolio_accounts(cycle_date):
            report.decisions.append(self.evaluate_account(account, cycle_date))
        report.elapsed_seconds = time.perf_counter() - started
        return report

    def evaluate_account(self, account: AccountDTO, cycle_date: date) -> AccountDecision:
        customer = self.repo.get_customer(account.customer_id)
        customer_name = customer.full_name if customer else account.customer_id

        history = [PeriodRecord(**h.model_dump()) for h in self.repo.get_period_history(account.account_id, cycle_date)]
        pending = self.repo.get_pending_payments(account.account_id, cycle_date)
        signals = compute_signals_for_account(Account(**account.model_dump()), history, cycle_date)
        raw_p, calibrated_p = self.model.evaluate_signals(signals)

        previous_band, consecutive = self._band_history(account.account_id, calibrated_p, cycle_date)
        hysteresis = apply_hysteresis(calibrated_p, previous_band, consecutive, self.policy)
        evidence = assess_evidence_quality(history, pending, cycle_date, self.policy.evidence_rules)
        band = hysteresis.confirmed_band
        days_to_due = (account.due_date - cycle_date).days

        decision_kwargs = dict(
            account_id=account.account_id,
            customer_name=customer_name,
            signals=signals,
            days_to_due=days_to_due,
        )
        action, rule, detail, extra = self._decide(
            account, customer, band, evidence, history, pending, cycle_date, days_to_due
        )

        evaluation = {
            "evaluation_id": f"EV-{cycle_date.isoformat()}-{account.account_id}",
            "account_id": account.account_id,
            "evaluation_date": cycle_date,
            "raw_probability": raw_p,
            "calibrated_probability": calibrated_p,
            "risk_band": band,
            "previous_risk_band": previous_band,
            "band_change_confirmed": hysteresis.band_change_confirmed,
            "evidence_quality": evidence,
            "action_type": action,
            "rule_applied": rule,
            "explanation": f"{hysteresis.explanation} {detail}".strip(),
        }
        self.repo.save_evaluation(evaluation)
        self.repo.save_audit_log(create_audit_entry(
            account_id=account.account_id,
            event_type="EVALUATION",
            actor="AGENT",
            payload={
                "cycle_date": cycle_date.isoformat(),
                "signals": signals.model_dump(mode="json"),
                "calibrated_probability": round(calibrated_p, 4),
                "risk_band": band.value,
                "hysteresis_rule": hysteresis.rule_applied,
                "evidence_quality": evidence.value,
                "action": action.value,
                "rule_applied": rule,
                "detail": detail,
            },
        ).model_dump())

        # El caso de revisión referencia la evaluación recién guardada (FK lógica).
        if extra.get("review_reason"):
            extra["review_case_id"] = self._open_review_case(
                account, band, days_to_due, evaluation["evaluation_id"],
                extra["review_reason"], extra.get("hypothesis", detail),
            )
        if extra.get("schedule"):
            notice_id, rejection = self._schedule(
                account, customer_name, band, evidence, evaluation, cycle_date, days_to_due, extra["schedule"]
            )
            extra["notice_id"] = notice_id
            extra["rejection_code"] = rejection
            if rejection:
                action, rule = ActionType.NO_ACTION, f"TOOL_REJECTED:{rejection}"
                detail = f"La herramienta rechazó el aviso ({rejection})."
            elif notice_id:
                action, rule = ActionType.SCHEDULE_NOTICE, "NOTICE_APPROVED"
                detail = f"Aviso {extra['schedule']['tone'].value} aprobado para las 10:00."
            if rejection or notice_id:
                evaluation.update(action_type=action, rule_applied=rule, explanation=f"{hysteresis.explanation} {detail}")
                self.repo.save_evaluation(evaluation)

        return AccountDecision(
            evaluation=evaluation,
            action=action,
            rule=rule,
            detail=detail,
            notice_id=extra.get("notice_id"),
            rejection_code=extra.get("rejection_code"),
            review_case_id=extra.get("review_case_id"),
            **decision_kwargs,
        )

    def _decide(self, account, customer, band, evidence, history, pending, cycle_date, days_to_due):
        """Devuelve (acción, regla, detalle, extra) sin efectos secundarios."""
        extra: Dict[str, Any] = {}
        if account.status == "PAID" or account.current_balance <= 0:
            return ActionType.NO_ACTION, "ALREADY_PAID", "La cuenta no tiene saldo pendiente.", extra
        if customer is not None and not customer.contact_enabled:
            return ActionType.NO_ACTION, "NO_CONSENT", "El cliente no autorizó el contacto.", extra

        if account.credit_limit > 0 and account.current_balance > account.credit_limit:
            extra.update(review_reason=REASON_OVER_LIMIT, hypothesis="El saldo supera el límite asignado.")
            return ActionType.ESCALATE_HUMAN, "OVER_LIMIT", REVIEW_REASON_TEXT[REASON_OVER_LIMIT], extra

        if evidence == EvidenceQuality.INCONSISTENT and not self._analyst_cleared(account.account_id):
            result = self.investigator.investigate(InvestigationContext(
                account_id=account.account_id,
                billed_amount=history[-1].billed_amount if history else account.minimum_payment,
                current_balance=account.current_balance,
                days_past_due=max(0, -days_to_due),
                pending_payments=pending,
                discrepancy_description="Pago en trámite no reflejado en el historial a la fecha de corte.",
                cutoff_date=cycle_date,
                minimum_payment=account.minimum_payment,
                tolerance_days=self.policy.evidence_rules.unreflected_payment_tolerance_days,
            ))
            if result.recommended_action == ACTION_WAIT_FOR_CLEARING:
                # Se suspende el contacto; el analista confirma la acreditación en la cola.
                extra.update(review_reason=REASON_PAYMENT_IN_PROCESS, hypothesis=result.explanation)
                return ActionType.NO_ACTION, "PAYMENT_IN_CLEARING", result.hypothesis, extra
            if result.recommended_action == ACTION_ESCALATE_HUMAN:
                extra.update(review_reason=REASON_UNEXPLAINED_PAYMENT, hypothesis=result.explanation)
                return ActionType.ESCALATE_HUMAN, "UNEXPLAINED_PAYMENT", result.hypothesis, extra

        effective_band = band
        tone_override: Optional[Tone] = None
        if evidence == EvidenceQuality.INSUFFICIENT:
            # RF-07: historial corto -> aviso neutro estándar, nunca por debajo de MODERADA.
            order = self.policy.band_order()
            effective_band = max(band, RiskBand.MODERADA, key=order.index)
            tone_override = Tone.NEUTRAL

        if days_to_due == 0:
            return ActionType.NO_ACTION, "DUE_TODAY", "Vence hoy: la política no autoriza avisos en el día del vencimiento.", extra

        preventive = days_to_due > 0
        window = get_contact_window(effective_band, preventive, self.policy)
        if not window.allowed or window.max_notices == 0:
            return ActionType.NO_ACTION, "NO_CONTACT_WINDOW", "La política no autoriza contacto en esta fase.", extra

        days_key = days_to_due if preventive else -days_to_due
        window_days = window.window_days_before_due if preventive else window.window_days_after_due
        if days_key not in window_days:
            if not preventive and days_key > max(window_days, default=0):
                return self._exhausted_or_idle(account, effective_band, cycle_date, extra)
            return ActionType.NO_ACTION, "OUTSIDE_WINDOW", "Fuera de la ventana de contacto autorizada.", extra

        if preventive:
            target = self.selector.choose(account.account_id, effective_band, window_days)
            if days_key > target:
                return ActionType.NO_ACTION, "WAITING_SEND_DAY", f"Se enviará a {target} días del vencimiento.", extra

        today_iso = cycle_date.isoformat()
        existing = [n for n in self.repo.get_notices(account.account_id)
                    if n["status"] in ACTIVE_NOTICE_STATUSES]
        if any(n["scheduled_date"][:10] == today_iso for n in existing):
            return ActionType.NO_ACTION, "ALREADY_SCHEDULED_TODAY", "Ya hay un aviso para hoy.", extra

        notices_in_phase = [n for n in existing
                            if (n["scheduled_date"][:10] < account.due_date.isoformat()) == preventive]
        if len(notices_in_phase) >= window.max_notices or (
            notices_in_phase and (cycle_date - date.fromisoformat(notices_in_phase[-1]["scheduled_date"][:10])).days
            < window.min_separation_days
        ):
            if not preventive and len(notices_in_phase) >= window.max_notices:
                extra.update(review_reason=REASON_NOTICES_EXHAUSTED,
                             hypothesis=f"Se envió {len(notices_in_phase)} aviso sin pago registrado." if len(notices_in_phase) == 1 else f"Se enviaron {len(notices_in_phase)} avisos sin pago registrado.")
                return ActionType.ESCALATE_HUMAN, "NOTICES_EXHAUSTED", REVIEW_REASON_TEXT[REASON_NOTICES_EXHAUSTED], extra
            return ActionType.NO_ACTION, "QUOTA_OR_SEPARATION", "Cuota o separación mínima de avisos no disponible hoy.", extra

        tone = tone_override or self._pick_tone(effective_band, preventive, window.allowed_tones)
        extra["schedule"] = {"band": effective_band, "tone": tone}
        return ActionType.SCHEDULE_NOTICE, "NOTICE_PENDING_TOOL", "Aviso propuesto a la herramienta.", extra

    def _exhausted_or_idle(self, account, band, cycle_date, extra):
        notices = [n for n in self.repo.get_notices(account.account_id) if n["status"] in ACTIVE_NOTICE_STATUSES]
        post = [n for n in notices if n["scheduled_date"][:10] > account.due_date.isoformat()]
        if post:
            extra.update(review_reason=REASON_NOTICES_EXHAUSTED,
                         hypothesis=f"Aviso(s) enviado(s): {len(post)}. Sin pago registrado y la ventana de contacto terminó.")
            return ActionType.ESCALATE_HUMAN, "NOTICES_EXHAUSTED", REVIEW_REASON_TEXT[REASON_NOTICES_EXHAUSTED], extra
        return ActionType.NO_ACTION, "OUTSIDE_WINDOW", "Fuera de la ventana de contacto autorizada.", extra

    @staticmethod
    def _pick_tone(band: RiskBand, preventive: bool, allowed: List[Tone]) -> Tone:
        if preventive and Tone.PREVENTIVE in allowed:
            return Tone.PREVENTIVE
        if not preventive and Tone.FIRM in allowed and band in (RiskBand.ALTA, RiskBand.CRITICA):
            return Tone.FIRM
        return Tone.NEUTRAL if Tone.NEUTRAL in allowed else allowed[0]

    def _band_history(self, account_id: str, calibrated_p: float, cycle_date: date):
        """Banda confirmada previa y ciclos consecutivos de la banda candidata (histéresis sin estado)."""
        prior = [e for e in self.repo.get_evaluations(account_id) if e["evaluation_date"][:10] < cycle_date.isoformat()]
        previous_band = RiskBand(prior[0]["risk_band"]) if prior else None
        candidate = classify_risk_band(calibrated_p, self.policy)
        consecutive = 1
        for e in prior:
            if classify_risk_band(float(e["calibrated_probability"]), self.policy) != candidate:
                break
            consecutive += 1
        return previous_band, consecutive

    # ------------------------------------------------------------------
    # Cola de revisión y auditoría
    # ------------------------------------------------------------------

    def _analyst_cleared(self, account_id: str) -> bool:
        return bool(self.repo.get_audit_logs(account_id, "REVIEW_RESOLVED"))

    def _open_review_case(self, account, band, days_to_due, evaluation_id, reason_code, hypothesis) -> str:
        case_id = f"CASE-{account.account_id}-{reason_code}"
        already = any(c["case_id"] == case_id for c in self.repo.get_review_queue())
        resolved = any(
            (log["payload"] or {}).get("case_id") == case_id
            for log in self.repo.get_audit_logs(account.account_id, "REVIEW_RESOLVED")
        )
        if not already and not resolved:
            self.repo.save_review_case({
                "case_id": case_id,
                "account_id": account.account_id,
                "evaluation_id": evaluation_id,
                "days_to_due": days_to_due,
                "risk_band": band,
                "reason": REVIEW_REASON_TEXT[reason_code],
                "agent_hypothesis": hypothesis,
                "status": "PENDING",
                "created_at": datetime.now(),
            })
        return case_id

    # ------------------------------------------------------------------
    # Programación del aviso (siempre vía ScheduleNoticeTool)
    # ------------------------------------------------------------------

    def _schedule(self, account, customer_name, band, evidence, evaluation, cycle_date, days_to_due, plan):
        context = DraftContext(
            client_reference=account.account_id,
            tone=plan["tone"],
            days_to_due=days_to_due,
            amount_due=account.minimum_payment,
            due_date_str=format_due_date(account.due_date),
        )
        message = compose_notice_message(context, customer_name=customer_name, drafter=self.drafter)
        output = self.tool.run(ScheduleNoticeInput(
            account_id=account.account_id,
            evaluation_id=evaluation["evaluation_id"],
            risk_band=plan["band"],
            scheduled_date=cycle_date,
            tone=message.tone,
            subject=message.subject,
            body_text=message.body_text,
        ))
        if not output.success:
            self.repo.save_audit_log(create_audit_entry(
                account_id=account.account_id,
                event_type="TOOL_REJECTION",
                actor="TOOL_GUARD",
                payload={"cycle_date": cycle_date.isoformat(), "code": output.rejection_code, "message": output.message},
            ).model_dump())
            return None, output.rejection_code
        if message.validation_status != "PASSED":
            self._set_validation_status(output.notice_id, message.validation_status)
        self.repo.save_audit_log(create_audit_entry(
            account_id=account.account_id,
            event_type="TOOL_CHECK",
            actor="TOOL_GUARD",
            payload={"cycle_date": cycle_date.isoformat(), "notice_id": output.notice_id,
                     "tone": message.tone.value, "validation": message.validation_status},
        ).model_dump())
        return output.notice_id, None

    def _set_validation_status(self, notice_id: str, status: str) -> None:
        for notice in self.repo.get_notices():
            if notice["notice_id"] == notice_id:
                notice["validation_status"] = status
                self.repo.save_notice(notice)
                return

    # ------------------------------------------------------------------
    # Despacho (10:00)
    # ------------------------------------------------------------------

    def close_review_and_dispatch(self, cycle_date: date, dispatcher: NoticeDispatcher) -> DispatchReport:
        report = DispatchReport(cycle_date=cycle_date)
        pending_accounts = {c["account_id"] for c in self.repo.get_review_queue()}
        today = cycle_date.isoformat()
        for notice in self.repo.get_notices():
            if notice["status"] != NoticeStatus.APPROVED.value or notice["scheduled_date"][:10] != today:
                continue
            account = self.repo.get_account(notice["account_id"])
            customer = self.repo.get_customer(account.customer_id) if account else None
            held_reason = None
            if notice["account_id"] in pending_accounts:
                held_reason = "RETENIDO: caso sin revisar al cierre de las 09:00"
            elif account is None or account.status == "PAID" or account.current_balance <= 0:
                held_reason = "CANCELADO: el cliente ya pagó"
            elif customer is None or not customer.contact_enabled:
                held_reason = "CANCELADO: sin consentimiento de contacto"
            if held_reason:
                self._hold(notice, held_reason, report)
                continue
            try:
                status = dispatcher.send(notice, customer.email)
            except Exception as exc:  # un fallo del proveedor no debe frenar el resto del despacho
                self._hold(notice, f"FALLO DE ENVÍO: {type(exc).__name__}", report)
                continue
            notice.update(status=status, sent_at=datetime.now())
            self.repo.save_notice(notice)
            report.sent.append(notice["notice_id"])
            self.repo.save_audit_log(create_audit_entry(
                account_id=notice["account_id"],
                event_type="DISPATCH",
                actor="AGENT",
                payload={"notice_id": notice["notice_id"], "status": status, "scheduled_date": today},
            ).model_dump())
        return report

    def _hold(self, notice: Dict[str, Any], reason: str, report: DispatchReport) -> None:
        notice.update(status=NoticeStatus.REJECTED.value, rejection_reason=reason)
        self.repo.save_notice(notice)
        report.held[notice["notice_id"]] = reason
        self.repo.save_audit_log(create_audit_entry(
            account_id=notice["account_id"],
            event_type="TOOL_REJECTION",
            actor="AGENT",
            payload={"notice_id": notice["notice_id"], "reason": reason},
        ).model_dump())

    def cancel_notices(self, account_id: str, from_date: date, reason: str) -> int:
        """Anula avisos aprobados aún no despachados (usado tras una reevaluación)."""
        cancelled = 0
        for notice in self.repo.get_notices(account_id):
            if notice["status"] in (NoticeStatus.APPROVED.value, NoticeStatus.SCHEDULED.value) \
                    and notice["scheduled_date"][:10] >= from_date.isoformat():
                notice.update(status=NoticeStatus.REJECTED.value, rejection_reason=reason)
                self.repo.save_notice(notice)
                cancelled += 1
        return cancelled
