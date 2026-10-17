"""Hoy: decisiones que esperan revisión antes de las 09:00 y lo que hace el agente solo."""

import streamlit as st

from src.simulation.engine import PHASE_REVIEW
from src.ui import services, theme

MAX_CASES = 5


def render() -> None:
    ctx = services.get_context()
    cases = services.review_cases(ctx)
    frame = services.portfolio_frame(ctx)
    counts = services.todays_notice_counts(ctx)
    in_review = ctx.engine.phase == PHASE_REVIEW

    n = len(cases)
    if not in_review:
        headline = "Día cerrado: " + (f"{counts['enviados']} recordatorios enviados" if counts["enviados"] != 1 else "1 recordatorio enviado")
        lead = "Pasa al día siguiente para ver las nuevas decisiones."
        if n:
            lead = f"{n} caso{'s' if n != 1 else ''} sin revisar se quedó sin enviar hoy. " + lead
    elif n == 0:
        headline, lead = "Nada pendiente de revisión", "El agente ya dejó listos los recordatorios de las 10:00."
    else:
        headline = f"{n} {'decisión' if n == 1 else 'decisiones'} para antes de las 09:00"
        lead = "Lo que no revises a tiempo no se envía hoy."

    button = '<div><a class="btn btn-primary" href="/por-revisar" target="_self">Empezar revisión →</a></div>' if n else ""
    rows = [
        theme.case_row(
            f"/por-revisar?case={c['case_id']}",
            c["customer_name"],
            theme.tag(theme.when_text(c["days_to_due"]), "t-urgent" if theme.is_urgent(c["days_to_due"]) else "t-soon"),
            c["reason"],
        )
        for c in cases[:MAX_CASES]
    ]
    if n > MAX_CASES:
        rows.append(
            '<a class="case" href="/por-revisar" target="_self" style="background:#FAFAF8">'
            f'<span class="small muted">{n - MAX_CASES} {'caso' if n - MAX_CASES == 1 else 'casos'} más en la cola</span>'
            '<span class="small" style="color:#1F3FBF;font-weight:500">Ver todos →</span></a>'
        )
    cases_html = f'<section class="card" style="overflow:hidden">{"".join(rows)}</section>' if rows else ""

    early = int(frame["Señal temprana"].sum()) if not frame.empty else 0
    reminders = counts["programados"] + counts["enviados"]
    no_action = int(((frame["Acción"] != "SCHEDULE_NOTICE") & ~frame["En revisión"]).sum()) if not frame.empty else 0
    tiles = "".join([
        theme.tile(reminders, "Recordatorios a las 10:00" if in_review else "Recordatorios enviados a las 10:00",
                   "Salen a las 10:00." if in_review else "Ya están en la bandeja de captura.", "/notificaciones"),
        theme.tile(early, "Señales tempranas", "Buenos pagadores con señales de deterioro. Se avisan antes.", "/clientes?filtro=senales"),
        theme.tile(no_action, "Sin acción", "No necesitan aviso.", muted=True),
    ])

    st.markdown(
        f'<main class="page"><section class="hero"><h1>{theme.esc(headline)}</h1>'
        f'<p class="muted">{theme.esc(lead)}</p>{button}</section>{cases_html}'
        f'<section class="stack"><h2 class="section-title">Lo hace el agente</h2><div class="tiles">{tiles}</div></section></main>',
        unsafe_allow_html=True,
    )
