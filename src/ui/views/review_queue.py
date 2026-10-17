"""Por revisar: cola de casos con formulario de corrección y reevaluación inmediata (RF-13)."""


import streamlit as st

from src.ui import services, theme


def _facts(ctx, case) -> str:
    account = ctx.repo.get_account(case["account_id"])
    pending = ctx.repo.get_pending_payments(account.account_id, ctx.engine.current_date)
    notices = [n for n in ctx.repo.get_notices(account.account_id) if n["status"] in ("DISPATCHED", "CAPTURED")]
    pending_text = "; ".join(
        f"{theme.money(p.amount)} el {p.payment_date.strftime('%d/%m')} ({'en proceso' if p.status == 'IN_PROCESS' else p.status.lower()})"
        for p in pending
    ) or "Ninguno"
    items = [
        ("Saldo", theme.money(account.current_balance)),
        ("Pago mínimo", theme.money(account.minimum_payment)),
        ("Vencimiento", theme.when_text((account.due_date - ctx.engine.current_date).days)),
        ("Pagos en trámite", pending_text),
        ("Avisos enviados", str(len(notices))),
    ]
    return '<div class="kv">' + "".join(
        f'<div><div class="k">{k}</div><div class="v" style="font-size:15px">{theme.esc(v)}</div></div>' for k, v in items
    ) + "</div>"


def render() -> None:
    ctx = services.get_context()
    cases = services.review_cases(ctx)
    st.markdown('<main class="page" style="gap:12px"><section class="hero"><h1>Por revisar</h1>'
                '<p class="muted">Casos que el agente no resuelve solo. Corrige el dato y reevalúa al instante.</p></section></main>',
                unsafe_allow_html=True)
    result = st.session_state.pop("review_result", None)
    if result:
        st.success(result)
    if not cases:
        st.markdown('<div class="card card-pad" style="margin-top:32px"><p class="muted">No hay casos pendientes.</p></div>',
                    unsafe_allow_html=True)
        return

    selected_id = st.query_params.get("case", cases[0]["case_id"])
    case = next((c for c in cases if c["case_id"] == selected_id), cases[0])

    theme.spacer(32)
    left, right = st.columns([5, 7], gap="large")
    with left:
        rows = [
            theme.case_row(
                f"/por-revisar?case={c['case_id']}", c["customer_name"],
                theme.tag(theme.when_text(c["days_to_due"]), "t-urgent" if theme.is_urgent(c["days_to_due"]) else "t-soon"),
                c["reason"], selected=c["case_id"] == case["case_id"],
            )
            for c in cases
        ]
        st.markdown(f'<section class="card" style="overflow:hidden">{"".join(rows)}</section>', unsafe_allow_html=True)

    with right:
        st.markdown(
            f'<div class="card card-pad stack"><h2 class="section-title">{theme.esc(case["customer_name"])}</h2>'
            f'<div>{theme.tag(theme.when_text(case["days_to_due"]), "t-urgent" if theme.is_urgent(case["days_to_due"]) else "t-soon")} '
            f'{theme.band_tag(case["risk_band"])}</div>'
            f'<p><strong>{theme.esc(case["reason"])}</strong></p>'
            f'<p class="small muted"><strong>Lo que concluyó el agente:</strong> {theme.esc(case["agent_hypothesis"])}</p>'
            f'{_facts(ctx, case)}</div>',
            unsafe_allow_html=True,
        )
        theme.spacer(16)
        _form(ctx, case)


def _form(ctx, case) -> None:
    pending = [p for p in ctx.repo.get_pending_payments(case["account_id"], ctx.engine.current_date) if p.status == "IN_PROCESS"]
    account = ctx.repo.get_account(case["account_id"])
    default_amount = float(pending[0].amount) if pending else float(account.minimum_payment)
    default_date = pending[0].payment_date if pending else ctx.engine.current_date
    with st.form(f"form-{case['case_id']}"):
        st.markdown("**Corregir y reevaluar**")
        confirmed = st.radio(
            "¿Se recibió el pago?",
            ["Sí, confirmar el pago", "No hay pago, seguir con la política"],
            key=f"radio-{case['case_id']}",
        )
        col1, col2 = st.columns(2)
        amount = col1.number_input("Monto pagado", min_value=0.0, value=default_amount, step=10.0, format="%.2f")
        paid_on = col2.date_input("Fecha del pago", value=default_date, max_value=ctx.engine.current_date)
        analyst = st.text_input("Analista", value="analista@demo.veraia.local")
        notes = st.text_area("Notas", placeholder="Opcional. Queda en la auditoría.")
        submitted = st.form_submit_button("Reevaluar", type="primary")
    if submitted:
        with_payment = confirmed.startswith("Sí")
        output = ctx.reevaluate.correct_payment_and_reevaluate(
            case_id=case["case_id"],
            account_id=case["account_id"],
            cutoff_date=ctx.engine.current_date,
            actor=analyst or "analista",
            notes=notes,
            payment_date=paid_on if with_payment else None,
            amount=amount if with_payment else None,
        )
        st.session_state["review_result"] = f"Caso resuelto. {output.summary}"
        st.query_params.clear()
        st.rerun()
