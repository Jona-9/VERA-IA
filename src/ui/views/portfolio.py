"""Clientes: cartera con alertas de riesgo y expediente detallado por cliente (RF-18)."""

import pandas as pd
import streamlit as st

from src.domain.entities import RiskBand, Tone
from src.tools.schedule_tool import ScheduleNoticeInput
from src.ui import services, theme

LIST_LIMIT = 30


def _summary(row) -> str:
    if row["Pagó"]:
        return "Sin saldo pendiente."
    if row["En revisión"]:
        return "En revisión: el agente espera tu decisión."
    if row["Señal temprana"]:
        return "Buen pagador con uso alto y pagos mínimos sostenidos."
    return f"Saldo {theme.money(row['Saldo'])} · uso {row['Uso']:.0%}"


def render() -> None:
    ctx = services.get_context()
    frame = services.portfolio_frame(ctx)

    st.markdown('<main class="page" style="gap:12px"><section class="hero"><h1>Clientes</h1>'
                '<p class="muted">La cartera a la fecha simulada, con la decisión más reciente del agente.</p></section></main>',
                unsafe_allow_html=True)
    theme.spacer(24)

    selected = st.query_params.get("cliente")
    if selected and selected in set(frame["account_id"]):
        _dossier(ctx, frame[frame["account_id"] == selected].iloc[0])
        return

    col_q, col_f = st.columns([3, 2])
    query = col_q.text_input("Buscar cliente", placeholder="Nombre o número de cuenta")
    filters = ["Todos", "Señales tempranas", "En revisión", "Riesgo alto o crítico", "Con saldo pendiente"]
    default = 1 if st.query_params.get("filtro") == "senales" else 0
    chosen = col_f.selectbox("Mostrar", filters, index=default)

    shown = frame
    if query:
        needle = query.lower()
        shown = shown[shown["Cliente"].str.lower().str.contains(needle) | shown["account_id"].str.lower().str.contains(needle)]
    if chosen == "Señales tempranas":
        shown = shown[shown["Señal temprana"]]
    elif chosen == "En revisión":
        shown = shown[shown["En revisión"]]
    elif chosen == "Riesgo alto o crítico":
        shown = shown[shown["Riesgo"].isin(["ALTA", "CRITICA"])]
    elif chosen == "Con saldo pendiente":
        shown = shown[~shown["Pagó"]]
    shown = shown.sort_values(["Pagó", "days_to_due", "Cliente"])

    st.markdown(f'<p class="small muted" style="margin:16px 0 8px">{len(shown)} de {len(frame)} clientes</p>', unsafe_allow_html=True)
    rows = []
    for _, row in shown.head(LIST_LIMIT).iterrows():
        tags = theme.band_tag(row["Riesgo"])
        if row["Señal temprana"]:
            tags += " " + theme.tag("Señal temprana", "t-info")
        if row["Pagó"]:
            tags = theme.tag("Pagó", "t-ok")
        rows.append(theme.case_row(f"/clientes?cliente={row['account_id']}", row["Cliente"], tags, _summary(row)))
    if rows:
        st.markdown(f'<section class="card" style="overflow:hidden">{"".join(rows)}</section>', unsafe_allow_html=True)
    else:
        st.markdown('<p class="muted">Ningún cliente coincide.</p>', unsafe_allow_html=True)
    if len(shown) > LIST_LIMIT:
        st.caption(f"Se muestran {LIST_LIMIT}; afina la búsqueda para ver el resto.")


def _dossier(ctx, row) -> None:
    day = ctx.engine.current_date
    account_id = row["account_id"]
    st.markdown('<a class="link-s" href="/clientes" target="_self">← Todos los clientes</a>', unsafe_allow_html=True)
    prob = f"{row['Probabilidad']:.0%}" if pd.notna(row["Probabilidad"]) else "—"
    items = [
        ("Saldo", theme.money(row["Saldo"])), ("Límite", theme.money(row["Límite"])), ("Uso de línea", f"{row['Uso']:.0%}"),
        ("Vencimiento", theme.when_text(row["days_to_due"])), ("Prob. de atraso", prob),
    ]
    kv = "".join(f'<div><div class="k">{k}</div><div class="v">{theme.esc(v)}</div></div>' for k, v in items)
    st.markdown(
        f'<div class="card card-pad stack" style="margin-top:12px"><h2 class="section-title" style="font-size:24px">{theme.esc(row["Cliente"])}</h2>'
        f'<p class="small muted">{theme.esc(account_id)} · {theme.esc(row["Correo"])}</p>'
        f'<div>{theme.band_tag(row["Riesgo"])} {theme.tag("Evidencia " + theme.EVIDENCE_LABEL.get(row["Evidencia"], row["Evidencia"]), "t-soon") if row["Evidencia"] != "—" else ""}</div>'
        f'<div class="kv">{kv}</div>'
        f'<p class="small muted"><strong>Decisión del agente:</strong> {theme.esc(theme.ACTION_LABEL.get(row["Acción"], row["Acción"]))} ({theme.esc(row["Regla"])}). {theme.esc(row["Explicación"])}</p></div>',
        unsafe_allow_html=True,
    )

    theme.spacer(24)
    st.markdown('<h3 class="section-title">Señales a la fecha de corte</h3>', unsafe_allow_html=True)
    s = row["signals"]
    st.dataframe(pd.DataFrame([{
        "Uso de línea": f"{s.credit_utilization_ratio:.0%}",
        "Pagos mínimos seguidos": s.consecutive_min_payments,
        "Pagado / facturado": f"{s.payment_to_billed_ratio:.0%}",
        "Caída del ratio de pago": f"{s.payment_ratio_drop:.0%}",
        "Períodos con atraso": f"{s.historical_delinquency_rate:.0%}",
        "Máximo días de atraso": s.max_past_due_days,
    }]), hide_index=True, use_container_width=True)

    history = ctx.repo.get_period_history(account_id, day)
    st.markdown('<h3 class="section-title" style="margin-top:24px">Historial de períodos</h3>', unsafe_allow_html=True)
    st.dataframe(pd.DataFrame([{
        "Período": h.period_index, "Facturado": h.billed_amount, "Pagado": h.paid_amount, "Vencía": h.due_date,
        "Pagó el": h.actual_payment_date, "Días de atraso": h.days_past_due, "Uso": f"{h.line_utilization:.0%}",
    } for h in history]), hide_index=True, use_container_width=True)

    notices = ctx.repo.get_notices(account_id)
    st.markdown('<h3 class="section-title" style="margin-top:24px">Avisos</h3>', unsafe_allow_html=True)
    if notices:
        rows = [theme.case_row("#", f"{n['scheduled_date'][:10]} · {theme.TONE_LABEL.get(n['tone'], n['tone'])}",
                               theme.notice_tag(n["status"]), n["rejection_reason"] or n["subject"]) for n in notices]
        st.markdown(f'<section class="card" style="overflow:hidden">{"".join(rows)}</section>', unsafe_allow_html=True)
    else:
        st.markdown('<p class="muted">Sin avisos todavía.</p>', unsafe_allow_html=True)

    st.markdown('<h3 class="section-title" style="margin-top:24px">Probar los límites de la herramienta</h3>'
                '<p class="small muted" style="margin-bottom:8px">Pide al agente un aviso adicional hoy. '
                'La herramienta decide: si rompe la política, lo rechaza con un código.</p>', unsafe_allow_html=True)
    if st.button("Intentar programar un aviso hoy", key=f"probe-{account_id}"):
        _probe(ctx, row)

    logs = ctx.repo.get_audit_logs(account_id)
    with st.expander(f"Auditoría ({len(logs)} eventos)"):
        st.dataframe(pd.DataFrame([{
            "Cuándo": l["timestamp"][:19].replace("T", " "), "Evento": l["event_type"], "Actor": l["actor"],
            "Detalle": str(l["payload"])[:200],
        } for l in logs]), hide_index=True, use_container_width=True)


def _probe(ctx, row) -> None:
    day = ctx.engine.current_date
    band = RiskBand(row["Riesgo"]) if row["Riesgo"] in RiskBand.__members__ else RiskBand.MODERADA
    tone = Tone.PREVENTIVE if row["days_to_due"] > 0 else Tone.FIRM
    evaluation_id = f"EV-{day.isoformat()}-{row['account_id']}"
    output = ctx.orchestrator.tool.run(ScheduleNoticeInput(
        account_id=row["account_id"], evaluation_id=evaluation_id, risk_band=band, scheduled_date=day, tone=tone,
        subject="Recordatorio de su cuota", body_text="Estimado(a) cliente: le recordamos su próxima cuota. Atentamente, Atención al Cliente.",
    ))
    if output.success:
        st.info(f"La política lo permite: aviso aprobado para las 10:00. {output.message}")
    else:
        st.error(f"Rechazado por la herramienta ({output.rejection_code}). {output.message}")
