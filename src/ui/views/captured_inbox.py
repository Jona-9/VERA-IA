"""Notificaciones: avisos del agente y bandeja de correos capturados por el SMTP local (RF-15)."""

from email import message_from_string, policy

import pandas as pd
import streamlit as st

from src.ui import services, theme

INBOX_LIMIT = 50


def _body(raw: str) -> str:
    message = message_from_string(raw, policy=policy.default)
    part = message.get_body(preferencelist=("plain",)) if message.is_multipart() else message
    return part.get_content() if part is not None else raw


def render() -> None:
    ctx = services.get_context()
    notices = services.notices_frame(ctx)
    emails = ctx.repo.get_captured_emails()

    st.markdown(
        '<main class="page" style="gap:12px"><section class="hero"><h1>Notificaciones</h1>'
        '<p class="muted">Lo que el agente programó y lo que llegó a la bandeja local. '
        'Esta bandeja es el único destino: ningún correo sale de este equipo.</p></section></main>',
        unsafe_allow_html=True,
    )
    theme.spacer(24)
    tab_notices, tab_inbox = st.tabs([f"Avisos ({len(notices)})", f"Bandeja de correos ({len(emails)})"])

    with tab_notices:
        if notices.empty:
            st.markdown('<p class="muted" style="padding:16px 0">Todavía no hay avisos.</p>', unsafe_allow_html=True)
        else:
            status = st.multiselect("Estado", sorted(notices["Estado"].unique()), key="notice-status", placeholder="Todos los estados")
            shown = notices[notices["Estado"].isin(status)] if status else notices
            rows = []
            for _, n in shown.sort_values(["Fecha", "Cliente"], ascending=[False, True]).iterrows():
                detail = n["Motivo"] if pd.notna(n["Motivo"]) and n["Motivo"] else f"{theme.TONE_LABEL.get(n['Tono'], n['Tono'])} · {n['Asunto']}"
                rows.append(theme.case_row(f"/clientes?cliente={n['account_id']}", n["Cliente"],
                                           theme.notice_tag(n["Estado"]), f"{n['Fecha']} · {detail}"))
            st.markdown(f'<section class="card" style="overflow:hidden">{"".join(rows)}</section>', unsafe_allow_html=True)

    with tab_inbox:
        if not emails:
            st.markdown('<p class="muted" style="padding:16px 0">La bandeja está vacía. Los correos aparecen aquí al enviar a las 10:00.</p>',
                        unsafe_allow_html=True)
        for email in emails[:INBOX_LIMIT]:
            with st.expander(f"{email['subject']} — {email['recipient']}"):
                st.markdown(f'<p class="small muted">De {theme.esc(email["sender"])} · {email["captured_at"][:16].replace("T", " ")}</p>'
                            f'<p class="mail-body">{theme.esc(_body(email["raw_content"]).strip()).replace(chr(10), "<br>")}</p>', unsafe_allow_html=True)
        if len(emails) > INBOX_LIMIT:
            st.caption(f"Se muestran los {INBOX_LIMIT} más recientes de {len(emails)}.")
