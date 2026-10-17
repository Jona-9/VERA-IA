"""Efectividad: agente adaptativo vs. campaña fija tradicional (RF-17, RF-18)."""

import json

import plotly.graph_objects as go
import streamlit as st

from src.simulation.benchmark import run_benchmark
from src.ui import services, theme

AGENT_COLOR = "#1F3FBF"
FIXED_COLOR = "#9AA0AA"


def _chart(title: str, labels, agent, fixed) -> go.Figure:
    fig = go.Figure([
        go.Bar(name="Agente", x=labels, y=agent, marker_color=AGENT_COLOR, text=agent, textposition="outside"),
        go.Bar(name="Campaña fija", x=labels, y=fixed, marker_color=FIXED_COLOR, text=fixed, textposition="outside"),
    ])
    fig.update_layout(
        title=dict(text=title, font=dict(size=16)), barmode="group", height=340, margin=dict(l=8, r=8, t=48, b=8),
        paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF", font=dict(family="Geist, system-ui, sans-serif", color="#111318"),
        legend=dict(orientation="h", y=-0.15), yaxis=dict(gridcolor="#EFEFEB", zeroline=False),
    )
    return fig


def render() -> None:
    ctx = services.get_context()
    st.markdown(
        '<main class="page" style="gap:12px"><section class="hero"><h1>Efectividad</h1>'
        '<p class="muted">El mismo grupo de clientes simulados, tratado de dos maneras: con el agente o con una campaña fija por segmento.</p>'
        '</section></main>', unsafe_allow_html=True,
    )
    theme.spacer(24)

    path = services.BENCHMARK_PATH
    if not path.exists():
        st.markdown('<div class="card card-pad"><p class="muted">Todavía no se calculó la comparación. '
                    'Recorre 21 días simulados con cada estrategia (unos 10 segundos).</p></div>', unsafe_allow_html=True)
        if st.button("Calcular comparación", type="primary"):
            with st.spinner("Simulando 21 días con cada estrategia…"):
                run_benchmark(ctx.model, ctx.policy, seed=services.SEED, cutoff_date=services.START_DATE,
                              customers=services.SIM_CUSTOMERS, output_path=path)
            st.rerun()
        return

    data = json.loads(path.read_text(encoding="utf-8"))
    agent, fixed = data["agent"], data["fixed"]
    reduction = data["low_moderate_reduction"]
    tiles = "".join([
        theme.tile(f"{reduction:.0%}", "Menos avisos a riesgo bajo y moderado", f"{agent['notices_low_moderate']} con el agente frente a {fixed['notices_low_moderate']} con la campaña fija.", muted=reduction < 0.25),
        theme.tile(f"{agent['avg_anticipation_days']:.1f} días", "Anticipación promedio del pago", f"Campaña fija: {fixed['avg_anticipation_days']:.1f} días. Entre quienes pagaron a tiempo."),
        theme.tile(f"{agent['on_time_rate']:.0%}", "Pago a tiempo", f"Campaña fija: {fixed['on_time_rate']:.0%}."),
    ])
    st.markdown(f'<div class="tiles">{tiles}</div>', unsafe_allow_html=True)
    theme.spacer(24)

    left, right = st.columns(2)
    with left:
        st.plotly_chart(_chart("Avisos enviados", ["Total", "Riesgo bajo/moderado"],
                               [agent["total_notices"], agent["notices_low_moderate"]],
                               [fixed["total_notices"], fixed["notices_low_moderate"]]), use_container_width=True)
    with right:
        st.plotly_chart(_chart("Pagos de clientes", ["Antes del vencimiento", "A tiempo (≤ vencimiento)"],
                               [agent["paid_before_due"], agent["paid_on_time"]],
                               [fixed["paid_before_due"], fixed["paid_on_time"]]), use_container_width=True)

    theme.spacer(16)
    st.markdown(
        f'<p class="small muted">Semilla {data["seed"]} · corte {data["cutoff_date"]} · {data["horizon_days"]} días · '
        f'{agent["accounts"]} clientes. Los avisos a clientes con pago en trámite fueron {agent["notices_while_payment_in_process"]} '
        f'con el agente y {fixed["notices_while_payment_in_process"]} con la campaña fija. '
        'La respuesta de los clientes es un supuesto del simulador, no evidencia real: las diferencias muestran el efecto de la '
        'política, no una promesa de resultados.</p>', unsafe_allow_html=True,
    )
    theme.spacer(16)
    if st.button("Recalcular"):
        path.unlink(missing_ok=True)
        st.rerun()
