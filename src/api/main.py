"""
API REST en FastAPI para VERAIA.
Sirve los datos del orquestador, simulación, cartera y benchmark
para el frontend en React + Vite + TypeScript.
"""

from __future__ import annotations

import json
from datetime import date
from email import message_from_string, policy
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.domain.entities import NoticeStatus, PeriodRecord, RiskBand, Tone
from src.simulation.benchmark import run_benchmark
from src.simulation.engine import PHASE_REVIEW
from src.tools.schedule_tool import ScheduleNoticeInput
from src.ui import services, theme

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIST = ROOT / "frontend" / "dist"

app = FastAPI(title="VERAIA API", version="1.0.0")

# CORS middleware for development Vite server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _get_ctx():
    return services.get_context()


def _body(raw: str) -> str:
    message = message_from_string(raw, policy=policy.default)
    part = message.get_body(preferencelist=("plain",)) if message.is_multipart() else message
    return part.get_content() if part is not None else raw


# ---------------------------------------------------------------------------
# Status & Simulation Controls
# ---------------------------------------------------------------------------

@app.get("/api/status")
def get_status() -> Dict[str, Any]:
    ctx = _get_ctx()
    engine = ctx.engine
    in_review = engine.phase == PHASE_REVIEW
    review_queue = ctx.repo.get_review_queue()
    header_note = f"{theme.day_label(engine.current_date)} · " + (
        "revisión hasta las 09:00" if in_review else "avisos enviados a las 10:00"
    )
    return {
        "day_number": engine.day_number,
        "current_date": engine.current_date.isoformat(),
        "date_label": theme.day_label(engine.current_date),
        "phase": engine.phase,
        "in_review": in_review,
        "header_note": header_note,
        "review_count": len(review_queue),
        "smtp_ok": ctx.smtp_ok,
    }


@app.post("/api/simulation/close-day")
def close_day() -> Dict[str, Any]:
    ctx = _get_ctx()
    ctx.engine.close_day()
    return get_status()


@app.post("/api/simulation/advance-day")
def advance_day() -> Dict[str, Any]:
    ctx = _get_ctx()
    ctx.engine.advance_day()
    return get_status()


@app.post("/api/simulation/reset")
def reset_demo() -> Dict[str, Any]:
    services.reset_demo()
    return get_status()


# ---------------------------------------------------------------------------
# Today View
# ---------------------------------------------------------------------------

def _get_why_manual_approval(c: Dict[str, Any], account: Any, pending: List[Any]) -> str:
    case_id = c.get("case_id", "")
    reason = c.get("reason", "")
    if "PAYMENT_IN_PROCESS" in case_id or "Pago en proceso" in reason:
        pending_strs = [
            f"{theme.money(p.amount)} reportado el {p.payment_date.strftime('%d/%m')}"
            for p in pending
            if getattr(p, "status", "") == "IN_PROCESS"
        ]
        detail = f" ({', '.join(pending_strs)})" if pending_strs else ""
        return (
            f"El cliente presenta un pago en trámite{detail} no acreditado aún en el balance del banco. "
            "La política VERAIA exige validación humana para evitar contactar a un cliente que ya pagó "
            "o enviar un recordatorio indebido."
        )
    elif "OVER_LIMIT" in case_id or "supera el límite" in reason:
        return (
            "El saldo actual de la cuenta supera la línea de crédito autorizada. "
            "La política exige autorización manual de un analista antes de iniciar acciones de cobranza estándar."
        )
    elif "NOTICES_EXHAUSTED" in case_id or "agotaron" in reason:
        return (
            "Se alcanzó el límite máximo de avisos automáticos permitidos por política sin registro de pago. "
            "El caso debe ser derivado a gestión humana directa."
        )
    elif "UNEXPLAINED_PAYMENT" in case_id:
        return (
            "Existe una discrepancia no conciliada entre los comprobantes y el saldo de la cuenta. "
            "Requiere revisión manual de auditoría."
        )
    return (
        f"Requiere aprobación manual según política ({reason}). "
        f"{c.get('agent_hypothesis', '')}"
    ).strip()


def _enrich_case(ctx: Any, c: Dict[str, Any]) -> Dict[str, Any]:
    account = ctx.repo.get_account(c["account_id"])
    customer = ctx.repo.get_customer(account.customer_id) if account else None
    pending = ctx.repo.get_pending_payments(c["account_id"], ctx.engine.current_date)
    notices = [n for n in ctx.repo.get_notices(c["account_id"]) if n["status"] in ("DISPATCHED", "CAPTURED")]

    eval_id = c.get("evaluation_id", "")
    opened_date = eval_id[3:13] if eval_id.startswith("EV-") else (c.get("created_at") or "")[:10]
    sim_today = ctx.engine.current_date.isoformat()

    is_carryover = bool(opened_date and opened_date < sim_today)
    if is_carryover:
        try:
            d_diff = (ctx.engine.current_date - date.fromisoformat(opened_date[:10])).days
            status_label = "Arrastrado de ayer" if d_diff == 1 else f"Arrastrado ({d_diff}d en cola)"
        except Exception:
            status_label = "Arrastrado de ayer"
        status_code = "ARRAS_TRADO"
        status_css = "t-urgent"
    else:
        status_label = "Pendiente hoy"
        status_code = "PENDIENTE_HOY"
        status_css = "t-soon"

    customer_name = customer.full_name if customer else c["account_id"]
    balance_str = theme.money(account.current_balance) if account else "—"
    limit_str = theme.money(account.credit_limit) if account else "—"
    util_str = f"{(account.current_balance / account.credit_limit):.0%}" if (account and account.credit_limit) else "—"
    band_label = theme.BAND_LABEL.get(c.get("risk_band"), c.get("risk_band") or "—")

    customer_context = f"Saldo: {balance_str} · Límite: {limit_str} ({util_str} uso) · {band_label}"
    why_manual = _get_why_manual_approval(c, account, pending)

    pending_text = "; ".join(
        f"{theme.money(p.amount)} el {p.payment_date.strftime('%d/%m')} ({'en proceso' if p.status == 'IN_PROCESS' else p.status.lower()})"
        for p in pending
    ) or "Ninguno"

    in_process_pending = [p for p in pending if p.status == "IN_PROCESS"]
    default_amount = float(in_process_pending[0].amount) if in_process_pending else float(account.minimum_payment if account else 0.0)
    default_date = in_process_pending[0].payment_date.isoformat() if in_process_pending else ctx.engine.current_date.isoformat()

    facts = [
        {"k": "Saldo", "v": balance_str},
        {"k": "Pago mínimo", "v": theme.money(account.minimum_payment) if account else "—"},
        {"k": "Vencimiento", "v": theme.when_text((account.due_date - ctx.engine.current_date).days if account else c["days_to_due"])},
        {"k": "Pagos en trámite", "v": pending_text},
        {"k": "Avisos enviados", "v": str(len(notices))},
    ]

    return {
        "case_id": c["case_id"],
        "account_id": c["account_id"],
        "customer_name": customer_name,
        "days_to_due": c["days_to_due"],
        "when_text": theme.when_text(c["days_to_due"]),
        "is_urgent": theme.is_urgent(c["days_to_due"]) or is_carryover,
        "risk_band": c.get("risk_band"),
        "reason": c["reason"],
        "agent_hypothesis": c.get("agent_hypothesis", ""),
        "customer_context": customer_context,
        "why_manual_approval": why_manual,
        "status_code": status_code,
        "status_label": status_label,
        "status_css": status_css,
        "is_carryover": is_carryover,
        "opened_date": opened_date,
        "facts": facts,
        "default_amount": default_amount,
        "default_date": default_date,
    }


# ---------------------------------------------------------------------------
# Status & Simulation Controls
# ---------------------------------------------------------------------------

@app.get("/api/status")
def get_status() -> Dict[str, Any]:
    ctx = _get_ctx()
    engine = ctx.engine
    in_review = engine.phase == PHASE_REVIEW
    review_queue = ctx.repo.get_review_queue()
    accounts = ctx.repo.get_portfolio_accounts(engine.current_date)
    total_accounts = len(accounts)
    review_count = len(review_queue)
    resolved_by_ai = max(0, total_accounts - review_count)

    header_note = f"{theme.day_label(engine.current_date)} · " + (
        "revisión hoy" if in_review else "avisos enviados a las 10:00"
    )
    return {
        "day_number": engine.day_number,
        "current_date": engine.current_date.isoformat(),
        "date_label": theme.day_label(engine.current_date),
        "phase": engine.phase,
        "in_review": in_review,
        "header_note": header_note,
        "review_count": review_count,
        "total_portfolio": total_accounts,
        "resolved_by_ai": resolved_by_ai,
        "smtp_ok": ctx.smtp_ok,
    }


@app.post("/api/simulation/close-day")
def close_day() -> Dict[str, Any]:
    ctx = _get_ctx()
    ctx.engine.close_day()
    return get_status()


@app.post("/api/simulation/advance-day")
def advance_day() -> Dict[str, Any]:
    ctx = _get_ctx()
    ctx.engine.advance_day()
    return get_status()


@app.post("/api/simulation/reset")
def reset_demo() -> Dict[str, Any]:
    services.reset_demo()
    return get_status()


# ---------------------------------------------------------------------------
# Today View
# ---------------------------------------------------------------------------

@app.get("/api/today")
def get_today_data() -> Dict[str, Any]:
    ctx = _get_ctx()
    cases = services.review_cases(ctx)
    frame = services.portfolio_frame(ctx)
    counts = services.todays_notice_counts(ctx)
    in_review = ctx.engine.phase == PHASE_REVIEW

    total_accounts = len(frame) if not frame.empty else 60
    n = len(cases)
    pct = (n / total_accounts) if total_accounts > 0 else 0.0
    pct_str = f"{pct:.0%}"

    if not in_review:
        headline = f"Día cerrado: {counts['enviados']} recordatorios enviados a las 10:00"
        lead = "Pasa al día siguiente para ver las nuevas decisiones de la cartera."
        if n:
            lead = f"{n} caso{'s' if n != 1 else ''} sin revisar pasaron a la cola del siguiente día. " + lead
    elif n == 0:
        headline = f"Nada pendiente de revisión (0 de {total_accounts} clientes requieren revisión)"
        lead = "El agente ya resolvió el 100% de la cartera y dejó listos los recordatorios de las 10:00."
    else:
        headline = f"{n} de {total_accounts} clientes requieren tu decisión hoy ({pct_str} de la cartera)"
        lead = (
            f"El {100 - int(round(pct * 100))}% restante fue resuelto de forma 100% autónoma por el agente. "
            "Los casos no revisados hoy quedan retenidos y pasan a la cola del siguiente día."
        )

    formatted_cases = [_enrich_case(ctx, c) for c in cases]

    early = int(frame["Señal temprana"].sum()) if not frame.empty else 0
    reminders = counts["programados"] + counts["enviados"]
    no_action = int(((frame["Acción"] != "SCHEDULE_NOTICE") & ~frame["En revisión"]).sum()) if not frame.empty else 0

    return {
        "headline": headline,
        "lead": lead,
        "in_review": in_review,
        "total_portfolio": total_accounts,
        "review_count": n,
        "resolved_by_ai_count": max(0, total_accounts - n),
        "cases": formatted_cases,
        "counts": counts,
        "early_signals": early,
        "reminders": reminders,
        "no_action": no_action,
    }


# ---------------------------------------------------------------------------
# Review Queue
# ---------------------------------------------------------------------------

@app.get("/api/review-queue")
def get_review_queue() -> List[Dict[str, Any]]:
    ctx = _get_ctx()
    cases = services.review_cases(ctx)
    return [_enrich_case(ctx, c) for c in cases]


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@app.get("/api/dashboard")
def get_dashboard() -> Dict[str, Any]:
    ctx = _get_ctx()
    day = ctx.engine.current_date
    accounts = ctx.repo.get_portfolio_accounts(day)
    total_accounts = len(accounts)

    review_cases_list = services.review_cases(ctx)
    enriched_cases = [_enrich_case(ctx, c) for c in review_cases_list]

    pending_today = [c for c in enriched_cases if not c["is_carryover"]]
    pending_carryover = [c for c in enriched_cases if c["is_carryover"]]

    resolved_cases = []
    with ctx.repo._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT case_id, account_id, days_to_due, risk_band, reason, status, resolved_by, resolved_at, created_at
            FROM review_queue
            WHERE status != 'PENDING'
            ORDER BY resolved_at DESC
            LIMIT 15
            """
        )
        for r in cursor.fetchall():
            acc = ctx.repo.get_account(r["account_id"])
            cust = ctx.repo.get_customer(acc.customer_id) if acc else None
            resolved_cases.append({
                "case_id": r["case_id"],
                "account_id": r["account_id"],
                "customer_name": cust.full_name if cust else r["account_id"],
                "reason": r["reason"],
                "status": r["status"],
                "risk_band": r["risk_band"],
                "resolved_by": r["resolved_by"] or "analista",
                "resolved_at": (r["resolved_at"] or "")[:16].replace("T", " "),
            })

    total_pending = len(enriched_cases)
    resolved_by_ai = max(0, total_accounts - total_pending)
    resolved_by_ai_pct = round((resolved_by_ai / total_accounts * 100), 1) if total_accounts else 0
    human_review_pct = round((total_pending / total_accounts * 100), 1) if total_accounts else 0

    notice_counts = services.todays_notice_counts(ctx)
    benchmark_info = get_benchmark()

    return {
        "total_portfolio": total_accounts,
        "resolved_by_ai": resolved_by_ai,
        "resolved_by_ai_pct": resolved_by_ai_pct,
        "human_review_required": total_pending,
        "human_review_pct": human_review_pct,
        "cases_status": {
            "pending_total": total_pending,
            "pending_today": len(pending_today),
            "pending_carryover": len(pending_carryover),
            "resolved_count": len(resolved_cases),
        },
        "pending_cases": enriched_cases,
        "resolved_cases": resolved_cases,
        "notices_counts": notice_counts,
        "benchmark": benchmark_info,
    }


class ReevaluateInput(BaseModel):
    confirmed: bool
    amount: Optional[float] = None
    payment_date: Optional[str] = None
    analyst: Optional[str] = "analista@demo.veraia.local"
    notes: Optional[str] = ""


@app.post("/api/review-queue/{case_id}/reevaluate")
def reevaluate_case(case_id: str, data: ReevaluateInput) -> Dict[str, Any]:
    ctx = _get_ctx()
    cases = services.review_cases(ctx)
    case = next((c for c in cases if c["case_id"] == case_id), None)
    if not case:
        raise HTTPException(status_code=404, detail="Caso no encontrado")

    paid_on = date.fromisoformat(data.payment_date) if (data.confirmed and data.payment_date) else None
    output = ctx.reevaluate.correct_payment_and_reevaluate(
        case_id=case["case_id"],
        account_id=case["account_id"],
        cutoff_date=ctx.engine.current_date,
        actor=data.analyst or "analista",
        notes=data.notes or "",
        payment_date=paid_on,
        amount=data.amount if data.confirmed else None,
    )
    return {
        "success": True,
        "summary": output.summary,
    }


# ---------------------------------------------------------------------------
# Notices & Captured Inbox
# ---------------------------------------------------------------------------

@app.get("/api/notices")
def get_notices() -> List[Dict[str, Any]]:
    ctx = _get_ctx()
    frame = services.notices_frame(ctx)
    if frame.empty:
        return []
    result = []
    for _, row in frame.iterrows():
        result.append({
            "notice_id": row["notice_id"],
            "account_id": row["account_id"],
            "customer_name": row["Cliente"],
            "date": row["Fecha"],
            "tone": row["Tono"],
            "tone_label": theme.TONE_LABEL.get(row["Tono"], row["Tono"]),
            "status": row["Estado"],
            "status_label": theme.NOTICE_LABEL.get(row["Estado"], (row["Estado"], "t-soon"))[0],
            "status_css": theme.NOTICE_LABEL.get(row["Estado"], (row["Estado"], "t-soon"))[1],
            "subject": row["Asunto"],
            "body_text": row["Texto"],
            "validation_status": row["Validación"],
            "rejection_reason": row["Motivo"],
        })
    return result


@app.get("/api/emails")
def get_emails() -> List[Dict[str, Any]]:
    ctx = _get_ctx()
    emails = ctx.repo.get_captured_emails()
    out = []
    for email in emails:
        out.append({
            "email_id": email["email_id"],
            "sender": email["sender"],
            "recipient": email["recipient"],
            "subject": email["subject"],
            "body": _body(email["raw_content"]).strip(),
            "captured_at": email["captured_at"],
            "captured_date_label": email["captured_at"][:16].replace("T", " "),
        })
    return out


# ---------------------------------------------------------------------------
# Portfolio & Client Dossier
# ---------------------------------------------------------------------------

@app.get("/api/portfolio")
def get_portfolio(
    query: Optional[str] = Query(None),
    filter: Optional[str] = Query(None),
) -> Dict[str, Any]:
    ctx = _get_ctx()
    frame = services.portfolio_frame(ctx)
    if frame.empty:
        return {"total": 0, "clients": []}

    shown = frame
    if query:
        needle = query.lower()
        shown = shown[
            shown["Cliente"].str.lower().str.contains(needle)
            | shown["account_id"].str.lower().str.contains(needle)
        ]
    if filter == "Señales tempranas" or filter == "senales":
        shown = shown[shown["Señal temprana"]]
    elif filter == "En revisión" or filter == "revision":
        shown = shown[shown["En revisión"]]
    elif filter == "Riesgo alto o crítico" or filter == "alto_critico":
        shown = shown[shown["Riesgo"].isin(["ALTA", "CRITICA"])]
    elif filter == "Con saldo pendiente" or filter == "con_saldo":
        shown = shown[~shown["Pagó"]]

    shown = shown.sort_values(["Pagó", "days_to_due", "Cliente"])

    clients = []
    for _, row in shown.iterrows():
        summary = (
            "Sin saldo pendiente."
            if row["Pagó"]
            else "En revisión: el agente espera tu decisión."
            if row["En revisión"]
            else "Buen pagador con uso alto y pagos mínimos sostenidos."
            if row["Señal temprana"]
            else f"Saldo {theme.money(row['Saldo'])} · uso {row['Uso']:.0%}"
        )
        clients.append({
            "account_id": row["account_id"],
            "customer_name": row["Cliente"],
            "email": row["Correo"],
            "due_date": row["Vence"].isoformat() if hasattr(row["Vence"], "isoformat") else str(row["Vence"]),
            "days_to_due": row["days_to_due"],
            "when_text": theme.when_text(row["days_to_due"]),
            "is_urgent": theme.is_urgent(row["days_to_due"]),
            "balance": row["Saldo"],
            "balance_money": theme.money(row["Saldo"]),
            "credit_limit": row["Límite"],
            "limit_money": theme.money(row["Límite"]),
            "utilization": row["Uso"],
            "utilization_pct": f"{row['Uso']:.0%}",
            "status": row["Estado"],
            "paid": bool(row["Pagó"]),
            "risk_band": row["Riesgo"],
            "risk_label": theme.BAND_LABEL.get(row["Riesgo"], row["Riesgo"]),
            "risk_css": theme.BAND_CLASS.get(row["Riesgo"], "t-soon"),
            "probability": row["Probabilidad"],
            "probability_pct": f"{row['Probabilidad']:.0%}" if pd.notna(row["Probabilidad"]) else "—",
            "evidence": row["Evidencia"],
            "evidence_label": theme.EVIDENCE_LABEL.get(row["Evidencia"], row["Evidencia"]),
            "action": row["Acción"],
            "action_label": theme.ACTION_LABEL.get(row["Acción"], row["Acción"]),
            "rule": row["Regla"],
            "explanation": row["Explicación"],
            "in_review": bool(row["En revisión"]),
            "early_signal": bool(row["Señal temprana"]),
            "summary": summary,
        })

    return {
        "total_portfolio": len(frame),
        "total_filtered": len(shown),
        "clients": clients,
    }


@app.get("/api/portfolio/{account_id}")
def get_client_dossier(account_id: str) -> Dict[str, Any]:
    ctx = _get_ctx()
    frame = services.portfolio_frame(ctx)
    row_matches = frame[frame["account_id"] == account_id]
    if row_matches.empty:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    row = row_matches.iloc[0]

    signals = row["signals"]
    signals_dict = {
        "credit_utilization_ratio": f"{signals.credit_utilization_ratio:.0%}",
        "consecutive_min_payments": signals.consecutive_min_payments,
        "payment_to_billed_ratio": f"{signals.payment_to_billed_ratio:.0%}",
        "payment_ratio_drop": f"{signals.payment_ratio_drop:.0%}",
        "historical_delinquency_rate": f"{signals.historical_delinquency_rate:.0%}",
        "max_past_due_days": signals.max_past_due_days,
    }

    history_records = ctx.repo.get_period_history(account_id, ctx.engine.current_date)
    history = [
        {
            "period_index": h.period_index,
            "billed_amount": theme.money(h.billed_amount),
            "paid_amount": theme.money(h.paid_amount),
            "due_date": h.due_date.isoformat(),
            "actual_payment_date": h.actual_payment_date.isoformat() if h.actual_payment_date else "—",
            "days_past_due": h.days_past_due,
            "line_utilization": f"{h.line_utilization:.0%}",
        }
        for h in history_records
    ]

    notices_records = ctx.repo.get_notices(account_id)
    notices = [
        {
            "notice_id": n["notice_id"],
            "scheduled_date": n["scheduled_date"][:10],
            "tone": n["tone"],
            "tone_label": theme.TONE_LABEL.get(n["tone"], n["tone"]),
            "status": n["status"],
            "status_label": theme.NOTICE_LABEL.get(n["status"], (n["status"], "t-soon"))[0],
            "status_css": theme.NOTICE_LABEL.get(n["status"], (n["status"], "t-soon"))[1],
            "subject": n["subject"],
            "rejection_reason": n["rejection_reason"],
        }
        for n in notices_records
    ]

    logs = ctx.repo.get_audit_logs(account_id)
    audit = [
        {
            "timestamp": l["timestamp"][:19].replace("T", " "),
            "event_type": l["event_type"],
            "actor": l["actor"],
            "payload": str(l["payload"]),
        }
        for l in logs
    ]

    prob_pct = f"{row['Probabilidad']:.0%}" if pd.notna(row["Probabilidad"]) else "—"

    return {
        "account_id": account_id,
        "customer_name": row["Cliente"],
        "email": row["Correo"],
        "due_date": row["Vence"].isoformat() if hasattr(row["Vence"], "isoformat") else str(row["Vence"]),
        "days_to_due": row["days_to_due"],
        "when_text": theme.when_text(row["days_to_due"]),
        "is_urgent": theme.is_urgent(row["days_to_due"]),
        "balance": theme.money(row["Saldo"]),
        "credit_limit": theme.money(row["Límite"]),
        "utilization": f"{row['Uso']:.0%}",
        "probability_pct": prob_pct,
        "risk_band": row["Riesgo"],
        "risk_label": theme.BAND_LABEL.get(row["Riesgo"], row["Riesgo"]),
        "risk_css": theme.BAND_CLASS.get(row["Riesgo"], "t-soon"),
        "evidence": row["Evidencia"],
        "evidence_label": theme.EVIDENCE_LABEL.get(row["Evidencia"], row["Evidencia"]),
        "action": row["Acción"],
        "action_label": theme.ACTION_LABEL.get(row["Acción"], row["Acción"]),
        "rule": row["Regla"],
        "explanation": row["Explicación"],
        "signals": signals_dict,
        "history": history,
        "notices": notices,
        "audit": audit,
    }


@app.post("/api/portfolio/{account_id}/probe")
def probe_schedule_tool(account_id: str) -> Dict[str, Any]:
    ctx = _get_ctx()
    frame = services.portfolio_frame(ctx)
    row_matches = frame[frame["account_id"] == account_id]
    if row_matches.empty:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    row = row_matches.iloc[0]

    day = ctx.engine.current_date
    band = RiskBand(row["Riesgo"]) if row["Riesgo"] in RiskBand.__members__ else RiskBand.MODERADA
    tone = Tone.PREVENTIVE if row["days_to_due"] > 0 else Tone.FIRM
    evaluation_id = f"EV-{day.isoformat()}-{account_id}"

    output = ctx.orchestrator.tool.run(ScheduleNoticeInput(
        account_id=account_id,
        evaluation_id=evaluation_id,
        risk_band=band,
        scheduled_date=day,
        tone=tone,
        subject="Recordatorio de su cuota",
        body_text="Estimado(a) cliente: le recordamos su próxima cuota. Atentamente, Atención al Cliente.",
    ))

    return {
        "success": output.success,
        "rejection_code": output.rejection_code,
        "message": output.message,
    }


# ---------------------------------------------------------------------------
# Benchmark / Efectividad
# ---------------------------------------------------------------------------

@app.get("/api/benchmark")
def get_benchmark() -> Dict[str, Any]:
    path = services.BENCHMARK_PATH
    if not path.exists():
        return {"calculated": False}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        "calculated": True,
        "data": data,
    }


@app.post("/api/benchmark/run")
def calculate_benchmark() -> Dict[str, Any]:
    ctx = _get_ctx()
    path = services.BENCHMARK_PATH
    run_benchmark(
        ctx.model,
        ctx.policy,
        seed=services.SEED,
        cutoff_date=services.START_DATE,
        customers=services.SIM_CUSTOMERS,
        output_path=path,
    )
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        "calculated": True,
        "data": data,
    }


# ---------------------------------------------------------------------------
# Static frontend delivery (Production)
# ---------------------------------------------------------------------------

if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")

    @app.get("/")
    def serve_root():
        return FileResponse(FRONTEND_DIST / "index.html")

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Endpoint no encontrado")
        file_path = FRONTEND_DIST / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(FRONTEND_DIST / "index.html")
