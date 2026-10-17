"""
Tema visual de la interfaz, tomado del diseño de referencia `propose-design/Main.dc.html`
("Hoy · Cobranza temprana"): fondo #FAFAF8, tinta #111318, acento #1F3FBF, tarjetas blancas con
borde #E8E8E3 y radio 16, píldoras de 999px, tipografía Geist.

Streamlit renderiza los widgets por su cuenta; aquí se reestilizan para que coincidan con el
diseño y se ofrecen helpers que generan el HTML de las piezas del diseño (tarjetas, filas, etiquetas).
"""

from __future__ import annotations

import html
from datetime import date
from typing import Iterable, List, Optional

import streamlit as st

WEEKDAYS = ("Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom")
MONTHS = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")

BAND_LABEL = {"BAJA": "Riesgo bajo", "MODERADA": "Riesgo moderado", "ALTA": "Riesgo alto", "CRITICA": "Riesgo crítico"}
BAND_CLASS = {"BAJA": "t-ok", "MODERADA": "t-soon", "ALTA": "t-urgent", "CRITICA": "t-urgent"}
ACTION_LABEL = {"NO_ACTION": "Sin acción", "SCHEDULE_NOTICE": "Aviso programado", "INVESTIGATE": "Investigando",
                "ESCALATE_HUMAN": "Derivado a revisión", "—": "—"}
EVIDENCE_LABEL = {"SUFFICIENT": "suficiente", "INSUFFICIENT": "insuficiente", "INCONSISTENT": "inconsistente"}
TONE_LABEL = {"NEUTRAL": "Neutro", "PREVENTIVE": "Preventivo", "FIRM": "Firme"}
NOTICE_LABEL = {
    "SCHEDULED": ("Programado", "t-soon"),
    "APPROVED": ("Sale a las 10:00", "t-info"),
    "REJECTED": ("No enviado", "t-urgent"),
    "DISPATCHED": ("Enviado", "t-ok"),
    "CAPTURED": ("Recibido en bandeja", "t-ok"),
}

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&display=swap');
:root{--ink:#111318;--muted:#5F646D;--accent:#1F3FBF;--accent-dark:#16309A;--line:#E8E8E3}
html,body,.stApp,.stApp p,.stApp label,.stApp button,.stApp input,.stApp textarea,.stApp li,.stApp td,.stApp th,.stApp h1,.stApp h2,.stApp h3{font-family:'Geist',ui-sans-serif,system-ui,sans-serif}
.stApp{background:#FAFAF8;color:var(--ink);font-size:15px;line-height:1.5;-webkit-font-smoothing:antialiased}
[data-testid="stHeader"],[data-testid="stToolbar"],[data-testid="stSidebar"],[data-testid="stSidebarCollapsedControl"],#MainMenu,footer{display:none!important}
section.main,[data-testid="stMain"]{overflow-x:hidden}
[data-testid="stMainBlockContainer"],.block-container{max-width:1120px!important;padding:0 24px 56px!important}
[data-testid="stVerticalBlock"]{gap:0}
h1,h2,h3,p{margin:0}
h1,h2,h3,[data-testid="stMarkdownContainer"] h1,[data-testid="stMarkdownContainer"] h2,[data-testid="stMarkdownContainer"] h3{padding:0!important}
[data-testid="stMarkdownContainer"]{margin-bottom:0!important}
a,a:hover,a:focus{text-decoration:none!important}
a{color:#1F3FBF}a:hover{color:#16309A}
.sp{display:block;width:100%}.sp8{height:8px}.sp16{height:16px}.sp24{height:24px}.sp32{height:32px}
.vh-header{background:#fff;border-bottom:1px solid #ECECE8;margin-left:calc(50% - 50vw);margin-right:calc(50% - 50vw);margin-bottom:0}
.nav{max-width:1120px;margin:0 auto;padding:0 24px;min-height:64px;display:flex;align-items:center;justify-content:space-between;gap:12px 24px;flex-wrap:wrap}
.brand{display:flex;align-items:center;gap:10px;font-weight:600;color:#111318!important}
.links{display:flex;gap:4px;flex-wrap:wrap}
.lnk{display:inline-flex;align-items:center;gap:8px;min-height:40px;padding:0 14px;border-radius:999px;color:#4B5058!important;font-weight:500}
.lnk:hover{background:#F0F0EC;color:#111318!important}
.lnk-on,.lnk-on:hover{background:#111318;color:#fff!important}
.badge{font-size:12px;font-weight:600;background:#1F3FBF;color:#fff;border-radius:999px;padding:0 7px;line-height:20px}
.muted{color:var(--muted)}
.small{font-size:13px}
.page{display:flex;flex-direction:column;gap:40px;padding-top:48px}
.hero{display:flex;flex-direction:column;gap:20px;max-width:720px}
.hero h1,.hero p{padding:0!important;margin:0!important}
.hero h1{font-size:36px;font-weight:600;letter-spacing:-0.02em;line-height:1.15}
.hero p{font-size:17px}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;min-height:48px;padding:0 22px;border-radius:999px;font-weight:600;font-size:15px}
.btn-primary{background:#1F3FBF;color:#fff!important}.btn-primary:hover{background:#16309A}
.card{background:#fff;border:1px solid var(--line);border-radius:16px}
.card-pad{padding:22px}
.case{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:4px 16px;align-items:center;padding:16px 20px;color:#111318!important;border-top:1px solid #EFEFEB}
.case:first-child{border-top:0}
.case:hover{background:#F7F7F4}
.case-on{background:#F3F5FD}
.tag{display:inline-flex;align-items:center;font-size:12.5px;font-weight:500;border-radius:999px;padding:3px 10px;white-space:nowrap}
.t-urgent{background:#FCE7DA;color:#7A2E06}
.t-soon{background:#F1F1ED;color:#3E434B}
.t-ok{background:#E2F2E6;color:#1D5B32}
.t-info{background:#E6EBFA;color:#1F3FBF}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(280px,100%),1fr));gap:16px}
.tile{display:flex;flex-direction:column;gap:8px;padding:22px;color:#111318!important}
a.tile:hover{border-color:#C9CBD1}
.num{font-size:34px;font-weight:600;letter-spacing:-0.02em;line-height:1}
.link-s{color:#1F3FBF;font-weight:500;font-size:13px}
.section-title{font-size:18px!important;font-weight:600}
.stack{display:flex;flex-direction:column;gap:16px}
.kv{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:16px}
.kv .k{font-size:12.5px;color:var(--muted)}.kv .v{font-size:18px;font-weight:600}
.mail-body{white-space:pre-wrap;font-size:14.5px;line-height:1.6}
.vh-footer{border-top:1px solid #ECECE8;margin-top:56px;padding:16px 0}
/* Widgets de Streamlit con el lenguaje del diseño */
.stButton>button,.stFormSubmitButton>button,[data-testid^="stBaseButton"]{border-radius:999px!important;min-height:48px;padding:0 22px!important;font-weight:600!important;font-size:15px!important;border:1px solid #D9DADF;background:#fff;color:#111318}
[data-testid="stBaseButton-primary"],[data-testid="stBaseButton-primaryFormSubmit"]{background:#1F3FBF!important;color:#fff!important;border:0!important}
[data-testid="stBaseButton-primary"]:hover,[data-testid="stBaseButton-primaryFormSubmit"]:hover{background:#16309A!important}
[data-testid="stBaseButton-secondary"]:hover{border-color:#111318}
[data-testid="stForm"]{background:#fff;border:1px solid var(--line)!important;border-radius:16px;padding:20px}
.stTextInput input,.stNumberInput input,.stDateInput input,.stTextArea textarea,.stSelectbox [data-baseweb="select"]>div{border-radius:12px!important;border-color:#D9DADF!important;background:#fff}
[data-testid="stExpander"]{border:1px solid var(--line)!important;border-radius:16px!important;background:#fff}
.sim-bar{padding:12px 0}
@media (max-width:640px){.hero h1{font-size:28px}.page{padding-top:32px;gap:32px}}
"""


def inject_css() -> None:
    st.markdown(f"<style>{CSS}</style>", unsafe_allow_html=True)


def esc(value: object) -> str:
    return html.escape(str(value if value is not None else ""))


def day_label(day: date) -> str:
    return f"{WEEKDAYS[day.weekday()]} {day.day} {MONTHS[day.month - 1]}"


def when_text(days_to_due: int) -> str:
    if days_to_due > 1:
        return f"Vence en {days_to_due} días"
    if days_to_due == 1:
        return "Vence mañana"
    if days_to_due == 0:
        return "Vence hoy"
    if days_to_due == -1:
        return "Venció hace 1 día"
    return f"Venció hace {-days_to_due} días"


def is_urgent(days_to_due: int) -> bool:
    """Urgente: vence en 3 días o menos, o lleva 5 o más de atraso."""
    return days_to_due <= -5 or 0 <= days_to_due <= 3


def money(value: float) -> str:
    return "$" + f"{value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def tag(text: str, css: str = "t-soon") -> str:
    return f'<span class="tag {css}">{esc(text)}</span>'


def band_tag(band: Optional[str]) -> str:
    if not band or band == "—":
        return tag("Sin evaluar")
    return tag(BAND_LABEL.get(band, band), BAND_CLASS.get(band, "t-soon"))


def notice_tag(status: str) -> str:
    label, css = NOTICE_LABEL.get(status, (status, "t-soon"))
    return tag(label, css)


def nav_header(active: str, review_count: int, right_text: str) -> str:
    items = [("", "Hoy"), ("por-revisar", "Por revisar"), ("notificaciones", "Notificaciones"),
             ("clientes", "Clientes"), ("efectividad", "Efectividad")]
    links = []
    for path, label in items:
        badge = f' <span class="badge">{review_count}</span>' if path == "por-revisar" and review_count else ""
        css = "lnk lnk-on" if path == active else "lnk"
        links.append(f'<a class="{css}" href="/{path}" target="_self">{label}{badge}</a>')
    return (
        '<header class="vh-header"><div class="nav">'
        '<a class="brand" href="/" target="_self"><svg width="28" height="28" viewBox="0 0 28 28" aria-hidden="true">'
        '<rect width="28" height="28" rx="8" fill="#111318"></rect>'
        '<path d="M7 18l5-5 3 3 6-7" fill="none" stroke="#FFFFFF" stroke-width="2.2" stroke-linecap="round" '
        'stroke-linejoin="round"></path></svg>Cobranza temprana</a>'
        f'<nav class="links" aria-label="Principal">{"".join(links)}</nav>'
        f'<span class="small muted">{esc(right_text)}</span></div></header>'
    )


def case_row(href: str, name: str, tag_html: str, summary: str, selected: bool = False) -> str:
    css = "case case-on" if selected else "case"
    return (
        f'<a class="{css}" href="{href}" target="_self"><span style="font-weight:600">{esc(name)}</span>'
        f'{tag_html}<span class="small muted" style="grid-column:1/-1">{esc(summary)}</span></a>'
    )


def tile(number: object, title: str, text: str, href: Optional[str] = None, muted: bool = False) -> str:
    color = ' style="color:#5F646D"' if muted else ""
    link = '<span class="link-s" style="margin-top:4px">Ver →</span>' if href else ""
    body = (
        f'<span class="num"{color}>{esc(number)}</span><span style="font-weight:600">{esc(title)}</span>'
        f'<span class="small muted">{esc(text)}</span>{link}'
    )
    if href:
        return f'<a class="card tile" href="{href}" target="_self">{body}</a>'
    return f'<div class="card tile">{body}</div>'


def spacer(px: int = 24) -> None:
    """Espacio vertical (las alturas en línea no sobreviven al contenedor de Streamlit)."""
    st.markdown(f'<div class="sp sp{px}"></div>', unsafe_allow_html=True)


def footer() -> None:
    st.markdown(
        '<div class="vh-footer"><p class="small muted">Datos de ejemplo. Respuesta de clientes y revisión '
        'simuladas. Ningún correo sale de este equipo.</p></div>',
        unsafe_allow_html=True,
    )
