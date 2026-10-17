"""
Punto de entrada Streamlit: `streamlit run src/ui/app.py`.

Navegación y estilo siguen el diseño de referencia (Hoy · Por revisar · Notificaciones · Clientes)
más una vista de Efectividad para el benchmark. La barra de simulación avanza el día: a las 09:00
cierra la revisión y a las 10:00 despacha los avisos aprobados.
"""

import sys
from pathlib import Path

# `streamlit run src/ui/app.py` no agrega la raíz del repositorio al path.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st  # noqa: E402

from src.simulation.engine import PHASE_REVIEW  # noqa: E402
from src.ui import services, theme  # noqa: E402
from src.ui.views import benchmark_view, captured_inbox, portfolio, review_queue, today  # noqa: E402

st.set_page_config(page_title="Cobranza temprana", page_icon="📈", layout="centered", initial_sidebar_state="collapsed")
theme.inject_css()

pages = [
    st.Page(today.render, title="Hoy", url_path="", default=True),
    st.Page(review_queue.render, title="Por revisar", url_path="por-revisar"),
    st.Page(captured_inbox.render, title="Notificaciones", url_path="notificaciones"),
    st.Page(portfolio.render, title="Clientes", url_path="clientes"),
    st.Page(benchmark_view.render, title="Efectividad", url_path="efectividad"),
]
current = st.navigation(pages, position="hidden")
ctx = services.get_context()
engine = ctx.engine
in_review = engine.phase == PHASE_REVIEW

header_note = f"{theme.day_label(engine.current_date)} · " + ("revisión hasta las 09:00" if in_review else "avisos enviados a las 10:00")
st.markdown(theme.nav_header(current.url_path, len(ctx.repo.get_review_queue()), header_note), unsafe_allow_html=True)

theme.spacer(16)
with st.container():
    info, action, reset = st.columns([5, 4, 2], vertical_alignment="center")
    info.markdown(
        f'<p class="small muted sim-bar">Simulación · día {engine.day_number} · '
        f'{"esperando el cierre de revisión" if in_review else "día cerrado"}</p>',
        unsafe_allow_html=True,
    )
    if in_review:
        if action.button("Cerrar revisión y enviar a las 10:00", type="primary", use_container_width=True):
            with st.spinner("Enviando recordatorios…"):
                engine.close_day()
            st.rerun()
    elif action.button("Pasar al día siguiente", type="primary", use_container_width=True):
        with st.spinner("Evaluando la cartera…"):
            engine.advance_day()
        st.rerun()
    if reset.button("Reiniciar demo", use_container_width=True):
        services.reset_demo()
        st.rerun()

if not ctx.smtp_ok:
    st.warning("El puerto 1025 está ocupado: los correos no se capturarán en la bandeja local.")

current.run()
theme.footer()
