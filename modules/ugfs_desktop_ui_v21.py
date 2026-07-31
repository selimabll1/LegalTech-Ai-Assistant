from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
import html
import math
import re

import pandas as pd
import streamlit as st

from modules.pdf_extractor import save_uploaded_pdf
from modules.notifications_dashboard_section_v3 import (
    _pdf_path,
    _sync_missing_pdfs_headless,
    _sync_notifications_headless,
)
from modules.ugfs_desktop_ui_v1 import (
    DEFAULT_DB,
    _analysis_cache,
    _analysis_dialog,
    _date,
    _document_type,
    _excel_dialog,
    _load_state,
    _logo_path,
    _matches_query,
    _notification_company,
    _pdf_dialog,
    _priority_for,
    _run_alert_analysis,
    _source_name,
    _to_b64,
)


UGFS_DESKTOP_UI_VERSION = "ugfs_desktop_ui_preview_v21"


# ============================================================
# UI ONLY
# ============================================================

NAVY = "#061B2D"
NAVY_2 = "#082641"
BLUE = "#1266F1"
TEXT = "#13294B"
MUTED = "#6F8197"
BORDER = "#DCE6F1"
BG = "#F5F8FC"
SUCCESS = "#18B781"


def _svg(name: str) -> str:
    icons = {
        "home": """
<svg viewBox="0 0 24 24" aria-hidden="true">
<path d="M3.5 10.8 12 3.8l8.5 7v9.1a1.6 1.6 0 0 1-1.6 1.6h-4.4v-6.4h-5v6.4H5.1a1.6 1.6 0 0 1-1.6-1.6z"/>
</svg>""",
        "bell": """
<svg viewBox="0 0 24 24" aria-hidden="true">
<path d="M18 8.7a6 6 0 0 0-12 0c0 7-2.4 7-2.4 8.3h16.8C20.4 15.7 18 15.7 18 8.7Z"/>
<path d="M9.6 20.2h4.8"/>
</svg>""",
        "file": """
<svg viewBox="0 0 24 24" aria-hidden="true">
<path d="M6 2.8h8l4 4V21H6z"/>
<path d="M14 2.8V7h4M9 11h6M9 15h6"/>
</svg>""",
        "sparkles": """
<svg viewBox="0 0 24 24" aria-hidden="true">
<path d="m12 2 1.3 4.1L17 7.5l-3.7 1.4L12 13l-1.3-4.1L7 7.5l3.7-1.4Z"/>
<path d="m18.5 13 .8 2.5 2.2.8-2.2.9-.8 2.4-.8-2.4-2.2-.9 2.2-.8Z"/>
<path d="m5.2 14 .7 2.1 1.9.7-1.9.7-.7 2.1-.7-2.1-1.9-.7 1.9-.7Z"/>
</svg>""",
        "grid": """
<svg viewBox="0 0 24 24" aria-hidden="true">
<rect x="3" y="3" width="7" height="7" rx="1"/>
<rect x="14" y="3" width="7" height="7" rx="1"/>
<rect x="3" y="14" width="7" height="7" rx="1"/>
<rect x="14" y="14" width="7" height="7" rx="1"/>
</svg>""",
        "check": """
<svg viewBox="0 0 24 24" aria-hidden="true">
<path d="m5 12.5 4.2 4.2L19 7"/>
</svg>""",
        "download": """
<svg viewBox="0 0 24 24" aria-hidden="true">
<path d="M12 3v12M7.5 10.5 12 15l4.5-4.5M4 20h16"/>
</svg>""",
        "settings": """
<svg viewBox="0 0 24 24" aria-hidden="true">
<circle cx="12" cy="12" r="3"/>
<path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4v-.2a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1a1.7 1.7 0 0 0 1.9.3 1.7 1.7 0 0 0 1-1.6v-.2h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1Z"/>
</svg>""",
    }
    return icons[name]


def _inject_css() -> None:
    st.markdown(
        f"""
<style>
:root {{
  --navy: {NAVY};
  --navy2: {NAVY_2};
  --blue: {BLUE};
  --text: {TEXT};
  --muted: {MUTED};
  --border: {BORDER};
  --bg: {BG};
}}

html, body, [data-testid="stAppViewContainer"], .stApp {{
  background: var(--bg);
  color: var(--text);
}}

header[data-testid="stHeader"] {{
  background: transparent !important;
  height: 2.25rem !important;
}}

[data-testid="stToolbar"] {{
  opacity: .35;
}}

[data-testid="stMain"],
[data-testid="stMainBlockContainer"],
main .block-container {{
  width: 100% !important;
  max-width: 100% !important;
}}

main .block-container {{
  padding: .7rem 1rem 1rem !important;
}}

[data-testid="stSidebar"] {{
  background:
    radial-gradient(circle at 72% 8%, rgba(22,102,241,.20), transparent 24%),
    linear-gradient(180deg, #061B2D 0%, #071E34 55%, #041525 100%);
  border-right: 1px solid rgba(255,255,255,.08);
}}

/*
IMPORTANT: no min-width/max-width on the OUTER sidebar.
That allows Streamlit to collapse it normally and the main workspace
immediately expands to the available viewport width.
*/
[data-testid="stSidebar"] > div:first-child {{
  padding: 0 !important;
}}

[data-testid="stSidebar"] .block-container {{
  padding: .85rem .75rem 1rem !important;
}}

[data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] {{
  background: rgba(255,255,255,.045) !important;
  border: 1px dashed rgba(85,167,255,.45) !important;
  border-radius: 13px !important;
}}

[data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] * {{
  color: rgba(255,255,255,.84) !important;
}}

[data-testid="stSidebar"] .stButton > button {{
  border-radius: 9px !important;
  background: linear-gradient(180deg, #2085FF, #006BEF) !important;
  color: white !important;
  border: 1px solid rgba(255,255,255,.08) !important;
  min-height: 2.65rem !important;
  font-weight: 800 !important;
}}

.ugfs-brand {{
  display:flex;
  align-items:center;
  justify-content:center;
  padding:.35rem 0 .7rem;
}}

.ugfs-brand img {{
  width:92px;
  filter:drop-shadow(0 10px 25px rgba(26,121,255,.28));
}}

.ugfs-side-nav {{
  display:flex;
  flex-direction:column;
  gap:.28rem;
  margin: .95rem 0 1.15rem;
}}

.ugfs-side-nav a {{
  display:flex;
  align-items:center;
  gap:.72rem;
  text-decoration:none;
  color:rgba(255,255,255,.86);
  padding:.68rem .72rem;
  border-radius:9px;
  border:1px solid transparent;
  font-weight:700;
  font-size:.89rem;
  transition:background .18s ease,border-color .18s ease,transform .18s ease;
}}

.ugfs-side-nav a:hover {{
  background:rgba(255,255,255,.055);
  border-color:rgba(255,255,255,.08);
  transform:translateX(2px);
}}

.ugfs-side-nav a.active {{
  color:#fff;
  background:rgba(18,102,241,.15);
  border-color:#1266F1;
  box-shadow:0 8px 22px rgba(0,80,180,.17);
}}

.ugfs-side-nav .nav-icon {{
  width:20px;
  height:20px;
  flex:0 0 20px;
  color:#D5EBFF;
}}

.ugfs-side-nav .nav-icon svg {{
  width:20px;
  height:20px;
  fill:none;
  stroke:currentColor;
  stroke-width:1.75;
  stroke-linecap:round;
  stroke-linejoin:round;
}}

.nav-badge {{
  margin-left:auto;
  min-width:23px;
  height:23px;
  border-radius:999px;
  display:inline-flex;
  align-items:center;
  justify-content:center;
  background:#0D70F7;
  color:#fff;
  font-size:.72rem;
  font-weight:900;
}}

.sidebar-import-box {{
  border:1px solid rgba(86,170,255,.30);
  border-radius:12px;
  padding:.76rem .72rem .54rem;
  color:#fff;
  background:rgba(255,255,255,.03);
}}

.sidebar-import-title {{
  text-align:center;
  font-weight:850;
  font-size:.83rem;
}}

.sidebar-import-sub {{
  color:rgba(255,255,255,.67);
  text-align:center;
  font-size:.72rem;
  line-height:1.45;
  margin:.45rem 0 .2rem;
}}

.sidebar-company {{
  margin-top:1.2rem;
  color:rgba(255,255,255,.82);
  font-size:.78rem;
  font-weight:750;
  display:flex;
  align-items:center;
  gap:.45rem;
}}

.green-dot {{
  display:inline-block;
  width:8px;
  height:8px;
  border-radius:50%;
  background:{SUCCESS};
}}

.desktop-header {{
  background:rgba(255,255,255,.91);
  border:1px solid #E1E9F2;
  border-radius:16px;
  padding:1.05rem 1.2rem .92rem;
  box-shadow:0 10px 36px rgba(26,58,91,.065);
  margin-bottom:.75rem;
}}

.desktop-title {{
  color:#0B1733;
  font-size:1.62rem;
  font-weight:900;
  letter-spacing:-.025em;
  line-height:1.08;
}}

.desktop-subtitle {{
  color:#647993;
  margin-top:.33rem;
  font-size:.85rem;
  font-weight:600;
}}

.status-strip {{
  background:#F7FBFF;
  border:1px solid #CFE0F5;
  border-radius:10px;
  padding:.68rem .82rem;
  margin:.72rem 0 .78rem;
  display:flex;
  justify-content:space-between;
  gap:1rem;
  font-size:.78rem;
  color:#334A67;
}}

.status-strip strong {{
  color:#152B49;
}}

.workspace-panel {{
  background:#fff;
  border:1px solid #DEE7F0;
  border-radius:12px;
  box-shadow:0 7px 24px rgba(24,55,88,.045);
  overflow:hidden;
}}

.workspace-title {{
  min-height:52px;
  padding:.86rem 1rem .74rem;
  display:flex;
  justify-content:space-between;
  align-items:center;
  border-bottom:1px solid #E7EDF4;
}}

.workspace-title strong {{
  color:#142A47;
  font-size:.84rem;
  text-transform:uppercase;
  letter-spacing:.015em;
}}

.notification-header-grid {{
  display:grid;
  grid-template-columns:.84fr 1.40fr 1.30fr .84fr .58fr .80fr .78fr;
  gap:.50rem;
  padding:.62rem .70rem;
  color:#708399;
  font-size:.68rem;
  font-weight:800;
  border-bottom:1px solid #E7EDF4;
  background:#FBFCFE;
}}

[class*="st-key-desktop_row_"],
[class*="st-key-desktop_selected_row_"] {{
  border:1px solid #E4EBF2 !important;
  border-radius:0 !important;
  border-left:0 !important;
  border-right:0 !important;
  margin-top:-1px !important;
  padding:.18rem .30rem !important;
  background:#fff;
}}

[class*="st-key-desktop_selected_row_"] {{
  background:#EEF5FF !important;
  border-top-color:#B8D4FF !important;
  border-bottom-color:#B8D4FF !important;
  box-shadow:inset 3px 0 0 #1266F1;
}}

[class*="st-key-desktop_row_"] [data-testid="stHorizontalBlock"],
[class*="st-key-desktop_selected_row_"] [data-testid="stHorizontalBlock"] {{
  align-items:center;
  gap:.4rem !important;
}}

.row-source {{
  color:#162E4B;
  font-size:.78rem;
  font-weight:900;
  display:flex;
  align-items:center;
  gap:.42rem;
}}

.source-dot {{
  display:inline-block;
  width:8px;
  height:8px;
  border-radius:50%;
  background:#2676F3;
}}

.row-company {{
  color:#1B314D;
  font-size:.78rem;
  font-weight:850;
  line-height:1.2;
}}

.row-ref {{
  color:#7D8E9F;
  font-size:.64rem;
  margin-top:.13rem;
  overflow:hidden;
  text-overflow:ellipsis;
  white-space:nowrap;
}}

.row-type {{
  color:#344C66;
  font-size:.75rem;
  line-height:1.25;
}}

.row-date {{
  color:#263B55;
  font-size:.75rem;
  font-weight:700;
}}

.pdf-pill {{
  display:inline-flex;
  align-items:center;
  justify-content:center;
  min-width:42px;
  height:25px;
  padding:0 .42rem;
  border-radius:7px;
  background:#EDFAF4;
  color:#13855F;
  border:1px solid #C9EEDF;
  font-size:.66rem;
  font-weight:900;
}}

.pdf-pill.missing {{
  background:#F5F7F9;
  color:#7B8B9B;
  border-color:#E2E7EB;
}}

.priority {{
  display:inline-block;
  padding:.20rem .50rem;
  border-radius:7px;
  font-size:.65rem;
  font-weight:850;
  white-space:nowrap;
}}

.priority.high {{
  color:#D63E3E;
  background:#FFF0F0;
  border:1px solid #FFD2D2;
}}

.priority.medium {{
  color:#A76A00;
  background:#FFF6E6;
  border:1px solid #FFE1A9;
}}

.priority.low {{
  color:#2564C8;
  background:#EDF5FF;
  border:1px solid #CFE2FF;
}}

.priority.none {{
  color:#6E8194;
  background:#F3F6F8;
  border:1px solid #E2E8ED;
}}

.row-action .stButton > button {{
  min-height:2.05rem !important;
  height:2.05rem !important;
  border-radius:7px !important;
  font-size:.68rem !important;
  padding:.2rem .5rem !important;
}}

.detail-meta-grid {{
  display:grid;
  grid-template-columns:repeat(5,minmax(0,1fr));
  border-bottom:1px solid #E7EDF4;
}}

.detail-meta {{
  padding:.70rem .78rem;
  border-right:1px solid #EDF1F5;
}}

.detail-meta:last-child {{
  border-right:none;
}}

.meta-label {{
  color:#788BA1;
  font-size:.66rem;
  font-weight:700;
}}

.meta-value {{
  color:#172C48;
  font-size:.80rem;
  font-weight:850;
  margin-top:.23rem;
  overflow-wrap:anywhere;
}}

.summary-box {{
  color:#263A54;
  font-size:.82rem;
  line-height:1.62;
}}

.pdf-card {{
  border:1px solid #E5ECF3;
  border-radius:9px;
  padding:.60rem .68rem;
  background:#FCFDFE;
}}

.pdf-file {{
  color:#283C55;
  font-size:.76rem;
  font-weight:800;
  overflow-wrap:anywhere;
}}

.pdf-meta {{
  color:#7B8DA0;
  font-size:.66rem;
  margin-top:.15rem;
}}

.stButton > button,
.stDownloadButton > button {{
  border-radius:8px !important;
  min-height:2.65rem !important;
  font-weight:800 !important;
  border:1px solid #D6E1ED !important;
  box-shadow:none !important;
}}

.stButton > button[kind="primary"] {{
  background:linear-gradient(180deg,#1979FF,#0564E8) !important;
  color:#fff !important;
  border-color:#0564E8 !important;
}}

[data-testid="stTextInput"] input {{
  border-radius:8px !important;
  min-height:2.7rem;
  border:1px solid #D5E0EB !important;
  background:#fff !important;
}}

div[data-testid="stTabs"] button[role="tab"] {{
  font-size:.76rem;
  font-weight:800;
  color:#536A84;
}}

div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {{
  color:#1266F1;
}}

div[data-testid="stDialog"] > div {{
  border-radius:16px !important;
}}

.bottom-status {{
  margin-top:.8rem;
  padding:.62rem .15rem .05rem;
  border-top:1px solid #E5ECF3;
  display:flex;
  justify-content:space-between;
  gap:1rem;
  color:#60748A;
  font-size:.70rem;
}}

@media(max-width:1200px) {{
  .notification-header-grid {{
    grid-template-columns:.78fr 1.16fr 1.10fr .76fr .54fr .72fr .72fr;
  }}
  .detail-meta-grid {{
    grid-template-columns:1fr 1fr;
  }}
}}

@media(max-width:900px) {{
  .notification-header-grid {{
    display:none;
  }}
  .status-strip {{
    flex-direction:column;
  }}
}}
</style>
        """,
        unsafe_allow_html=True,
    )



_ARABIC_RE = re.compile(
    r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]"
)


def _contains_arabic(value: object) -> bool:
    return bool(_ARABIC_RE.search(str(value or "")))


def _bidi_html(value: object) -> str:
    """Escape text and isolate Arabic runs so mixed FR/AR stays readable."""
    text = str(value or "")
    escaped = html.escape(text)

    # Arabic letters + Arabic punctuation + spaces stay in an isolated RTL run.
    arabic_run = re.compile(
        r"([\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]"
        r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF"
        r"\s،؛؟ـ\(\)\[\]0-9\.\-\/]*"
        r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF])"
    )

    return arabic_run.sub(
        r'<span class="rtl-fragment" dir="rtl">\1</span>',
        escaped,
    )


def _legal_fields_html(fields: dict) -> str:
    rows = []
    for key, value in fields.items():
        if value in (None, ""):
            continue

        label = html.escape(
            str(key).replace("_", " ").strip().title()
        )
        direction = "rtl" if _contains_arabic(value) else "auto"
        rendered = _bidi_html(value)

        rows.append(
            f"<tr><th>{label}</th>"
            f"<td dir=\"{direction}\">{rendered}</td></tr>"
        )

    if not rows:
        return ""

    return (
        '<table class="legal-table">'
        + "".join(rows)
        + "</table>"
    )


def _parse_alert_date(value: object) -> date | None:
    raw = str(value or "").strip()
    if not raw:
        return None

    if "T" in raw:
        raw = raw.split("T", 1)[0]

    for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            pass

    return None


def _resolve_date_range(value):
    if not value:
        return None, None

    if isinstance(value, (list, tuple)):
        if len(value) == 1:
            return value[0], value[0]
        if len(value) >= 2:
            start, end = value[0], value[1]
            return min(start, end), max(start, end)

    return value, value


def _source_short(alert: dict) -> str:
    source = str(alert.get("source") or "").casefold()
    label = _source_name(alert).casefold()

    if source == "rne" or "registre national" in label:
        return "RNE"
    if source == "jort" or "journal officiel" in label:
        return "JORT"
    if "chourouk" in label:
        return "CHOUROUK"
    if "assabeh" in label:
        return "ASSABEH"
    if "quotidien" in label:
        return "QUOTIDIEN"
    if "temps" in label:
        return "LE TEMPS"
    if source.startswith("jr") or label.startswith("journal"):
        return "PRESSE"
    return _source_name(alert)[:18].upper()


def _reference(alert: dict) -> str:
    fields = alert.get("source_fields") or {}
    return str(
        fields.get("numero_publication")
        or fields.get("identifiant_unique")
        or alert.get("article_id")
        or ""
    )


def _sidebar(notification_count: int) -> None:
    with st.sidebar:
        logo = _logo_path()
        if logo:
            st.markdown(
                f"""
<div class="ugfs-brand">
  <img src="data:image/png;base64,{_to_b64(logo)}" />
</div>
                """,
                unsafe_allow_html=True,
            )

        nav_items = [
            ("home", "Accueil", "#home", False),
            ("bell", "Notifications", "#notifications", True),
            ("file", "Documents PDF", "#pdf-zone", False),
            ("sparkles", "Analyse IA", "#analysis-zone", False),
            ("grid", "Résultats", "#results-zone", False),
            ("check", "Corrections", "#corrections-zone", False),
            ("download", "Exports", "#exports-zone", False),
            ("settings", "Paramètres", "#settings-zone", False),
        ]

        nav_html = ['<div class="ugfs-side-nav">']
        for icon, label, href, active in nav_items:
            cls = "active" if active else ""
            badge = (
                f'<span class="nav-badge">{notification_count}</span>'
                if label == "Notifications"
                else ""
            )
            nav_html.append(
                f"""
<a class="{cls}" href="{href}">
  <span class="nav-icon">{_svg(icon)}</span>
  <span>{html.escape(label)}</span>
  {badge}
</a>
                """
            )
        nav_html.append("</div>")
        st.markdown("\n".join(nav_html), unsafe_allow_html=True)

        st.markdown(
            """
<div class="sidebar-import-box">
  <div class="sidebar-import-title">Importer des PDF</div>
  <div class="sidebar-import-sub">
    Glissez-déposez vos fichiers ici<br>
    ou cliquez pour importer<br><br>
    Max 200 Mo par fichier · PDF
  </div>
</div>
            """,
            unsafe_allow_html=True,
        )

        uploaded = st.file_uploader(
            "Importer des PDF",
            type=["pdf"],
            accept_multiple_files=True,
            label_visibility="collapsed",
            key="desktop_v2_sidebar_upload",
        )

        if uploaded and st.button(
            "Enregistrer les fichiers",
            width="stretch",
            key="desktop_v2_sidebar_save",
        ):
            for file in uploaded:
                save_uploaded_pdf(file)
            st.success(f"{len(uploaded)} PDF enregistré(s).")

        st.markdown(
            """
<div class="sidebar-company">
  <span class="green-dot"></span>
  UGFS North Africa
</div>
            """,
            unsafe_allow_html=True,
        )


def _render_header() -> None:
    st.markdown(
        """
<div class="desktop-header" id="home">
  <div class="desktop-title">Système de Veille LegalTech</div>
  <div class="desktop-subtitle">
    Notifications LegalTech &nbsp;•&nbsp; PDF &nbsp;•&nbsp; OCR
    &nbsp;•&nbsp; Analyse IA &nbsp;•&nbsp; Export Excel
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )


def _render_notification_row(
    alert: dict,
    *,
    selected: bool,
    row_index: int,
) -> bool:
    key_prefix = (
        f"desktop_selected_row_{row_index}"
        if selected
        else f"desktop_row_{row_index}"
    )

    with st.container(border=True, key=key_prefix):
        cols = st.columns(
            [0.84, 1.40, 1.30, 0.84, 0.58, 0.80, 0.78],
            gap="small",
        )

        with cols[0]:
            st.markdown(
                f"""
<div class="row-source">
  <span class="source-dot"></span>
  {html.escape(_source_short(alert))}
</div>
                """,
                unsafe_allow_html=True,
            )

        with cols[1]:
            st.markdown(
                f"""
<div class="row-company">{html.escape(_notification_company(alert))}</div>
<div class="row-ref">{html.escape(_reference(alert))}</div>
                """,
                unsafe_allow_html=True,
            )

        with cols[2]:
            st.markdown(
                f'<div class="row-type">{html.escape(_document_type(alert))}</div>',
                unsafe_allow_html=True,
            )

        with cols[3]:
            st.markdown(
                f'<div class="row-date">{html.escape(_date(alert))}</div>',
                unsafe_allow_html=True,
            )

        with cols[4]:
            pdf = _pdf_path(alert)
            cls = "" if pdf else "missing"
            label = "PDF" if pdf else "—"
            st.markdown(
                f'<span class="pdf-pill {cls}">{label}</span>',
                unsafe_allow_html=True,
            )

        with cols[5]:
            priority_label, priority_class = _priority_for(alert)
            st.markdown(
                f'<span class="priority {priority_class}">'
                f'{html.escape(priority_label)}</span>',
                unsafe_allow_html=True,
            )

        with cols[6]:
            st.markdown('<div class="row-action">', unsafe_allow_html=True)
            clicked = st.button(
                "Ouvrir",
                width="stretch",
                key=f"desktop_v2_open_{alert['alert_key']}_{row_index}",
            )
            st.markdown("</div>", unsafe_allow_html=True)

    return clicked


def render_ugfs_desktop_app_v21() -> None:
    _inject_css()

    if not DEFAULT_DB.exists():
        st.error(
            "La base notifications v5 n'existe pas encore. "
            "Lancez d'abord une synchronisation."
        )
        return

    run, notifications, alerts = _load_state()
    if not run:
        st.error("Aucune collecte LegalTech disponible.")
        return

    _sidebar(len(notifications))
    _render_header()

    st.markdown('<div id="notifications"></div>', unsafe_allow_html=True)

    # --------------------------------------------------------
    # Toolbar: same behavior, cleaner UI, no decorative glyphs.
    # --------------------------------------------------------
    search_col, filter_col, period_col, priority_col, sync_col, import_col = st.columns(
        [3.25, 1.05, 1.12, 1.02, 1.28, 1.48],
        gap="small",
    )

    with search_col:
        query = st.text_input(
            "Rechercher",
            placeholder="Rechercher (source, entreprise, identifiant…)",
            label_visibility="collapsed",
            key="desktop_v2_search",
        )

    source_options = sorted({_source_name(a) for a in alerts})
    type_options = sorted({_document_type(a) for a in alerts})

    with filter_col:
        with st.popover("Filtres", width="stretch"):
            selected_sources = st.multiselect(
                "Source",
                source_options,
                key="desktop_v2_filter_source",
            )
            selected_types = st.multiselect(
                "Type",
                type_options,
                key="desktop_v2_filter_type",
            )

    with period_col:
        with st.popover("Période", width="stretch"):
            date_filter = st.date_input(
                "Sélectionner une période",
                value=(),
                format="DD/MM/YYYY",
                key="desktop_v21_date_filter",
                help=(
                    "Choisissez une date unique ou une période. "
                    "Laissez vide pour afficher toutes les dates."
                ),
            )

    with priority_col:
        with st.popover("Priorité", width="stretch"):
            priority_filter = st.multiselect(
                "Priorité",
                ["Élevée", "Moyenne", "Faible", "À analyser"],
                key="desktop_v2_priority_filter",
            )

    with sync_col:
        if st.button(
            "Synchroniser",
            width="stretch",
            key="desktop_v2_sync",
        ):
            before = {
                (
                    str(n.get("company_or_query") or "").casefold(),
                    str(n.get("notification_date") or ""),
                )
                for n in notifications
            }

            with st.spinner("Synchronisation LegalTech en arrière-plan…"):
                ok, log = _sync_notifications_headless(10)

            st.session_state["desktop_v2_sync_log"] = log
            if ok:
                _, new_notifications, _ = _load_state()
                after = {
                    (
                        str(n.get("company_or_query") or "").casefold(),
                        str(n.get("notification_date") or ""),
                    )
                    for n in new_notifications
                }
                st.session_state["desktop_v2_new_notifications"] = list(
                    after - before
                )
                st.rerun()
            else:
                st.error("La synchronisation a échoué.")
                with st.expander("Journal"):
                    st.code(log or "Aucun journal.")

    with import_col:
        with st.popover("Importer des PDF", width="stretch"):
            top_upload = st.file_uploader(
                "PDF",
                type=["pdf"],
                accept_multiple_files=True,
                key="desktop_v2_top_upload",
            )

            if top_upload and st.button(
                "Enregistrer",
                width="stretch",
                key="desktop_v2_top_save",
            ):
                for file in top_upload:
                    save_uploaded_pdf(file)
                st.success(f"{len(top_upload)} PDF enregistré(s).")

            if st.button(
                "Récupérer les PDF manquants",
                width="stretch",
                key="desktop_v2_missing_pdfs",
            ):
                with st.spinner("Récupération des PDF manquants…"):
                    ok, log = _sync_missing_pdfs_headless()

                if ok:
                    st.success("Récupération PDF terminée.")
                    st.rerun()

                st.error("La récupération PDF a échoué.")
                with st.expander("Journal PDF"):
                    st.code(log or "Aucun journal.")

    new_items = st.session_state.get(
        "desktop_v2_new_notifications",
        [],
    )
    latest_sync = str(run.get("started_at") or "—")

    st.markdown(
        f"""
<div class="status-strip">
  <div><strong>Dernière synchronisation :</strong> {html.escape(latest_sync)}</div>
  <div><span class="green-dot"></span>&nbsp; {len(new_items)} nouvelle(s) notification(s)</div>
</div>
        """,
        unsafe_allow_html=True,
    )

    filtered = []
    for alert in alerts:
        if not _matches_query(alert, query.strip()):
            continue
        if selected_sources and _source_name(alert) not in selected_sources:
            continue
        if selected_types and _document_type(alert) not in selected_types:
            continue
        start_date, end_date = _resolve_date_range(date_filter)
        if start_date is not None:
            alert_date = _parse_alert_date(_date(alert))
            if alert_date is None:
                continue
            if alert_date < start_date:
                continue
            if end_date is not None and alert_date > end_date:
                continue

        priority_label, _ = _priority_for(alert)
        if priority_filter and priority_label not in priority_filter:
            continue

        filtered.append(alert)

    # ========================================================
    # CLEAN 42 / 58 SPLIT
    # ========================================================
    list_col, detail_col = st.columns([0.94, 1.24], gap="medium")

    selected_key = st.session_state.get("desktop_v2_selected_alert")

    with list_col:
        st.markdown(
            f"""
<div class="workspace-panel">
  <div class="workspace-title">
    <strong>Liste des notifications ({len(filtered)})</strong>
    <span style="color:#6D8197;font-size:.74rem;">Dernières alertes</span>
  </div>
  <div class="notification-header-grid">
    <div>Source</div>
    <div>Entreprise</div>
    <div>Type</div>
    <div>Date</div>
    <div>PDF</div>
    <div>Priorité</div>
    <div></div>
  </div>
</div>
            """,
            unsafe_allow_html=True,
        )

        page_size = st.session_state.get("desktop_v2_page_size", 10)
        total_pages = max(1, math.ceil(len(filtered) / page_size))
        current_page = int(st.session_state.get("desktop_v2_page", 1))
        current_page = min(max(1, current_page), total_pages)

        start = (current_page - 1) * page_size
        page_alerts = filtered[start:start + page_size]

        for row_index, alert in enumerate(page_alerts):
            is_selected = str(alert.get("alert_key")) == str(selected_key)

            if _render_notification_row(
                alert,
                selected=is_selected,
                row_index=start + row_index,
            ):
                st.session_state["desktop_v2_selected_alert"] = alert[
                    "alert_key"
                ]
                st.rerun()

        p1, p2, p3, p4 = st.columns([1.45, 1.05, .72, .72])

        with p1:
            st.caption(
                f"Affichage {start + 1 if filtered else 0} à "
                f"{min(start + page_size, len(filtered))} sur {len(filtered)}"
            )

        with p2:
            selected_page_size = st.selectbox(
                "Lignes par page",
                [5, 10, 15, 20],
                index=[5, 10, 15, 20].index(page_size),
                label_visibility="collapsed",
                key="desktop_v2_page_size_widget",
            )
            if selected_page_size != page_size:
                st.session_state["desktop_v2_page_size"] = selected_page_size
                st.session_state["desktop_v2_page"] = 1
                st.rerun()

        with p3:
            if st.button(
                "Préc.",
                width="stretch",
                disabled=current_page <= 1,
                key="desktop_v2_prev",
            ):
                st.session_state["desktop_v2_page"] = current_page - 1
                st.rerun()

        with p4:
            if st.button(
                "Suiv.",
                width="stretch",
                disabled=current_page >= total_pages,
                key="desktop_v2_next",
            ):
                st.session_state["desktop_v2_page"] = current_page + 1
                st.rerun()

        st.caption(f"Page {current_page} / {total_pages}")

    if selected_key:
        selected = next(
            (
                item
                for item in alerts
                if str(item.get("alert_key")) == str(selected_key)
            ),
            None,
        )
    else:
        selected = filtered[0] if filtered else None

    if selected and not selected_key:
        st.session_state["desktop_v2_selected_alert"] = selected["alert_key"]

    with detail_col:
        if not selected:
            st.info("Sélectionnez une alerte pour afficher son détail.")
        else:
            priority_label, priority_class = _priority_for(selected)
            fields = selected.get("source_fields") or {}
            pdf = _pdf_path(selected)
            analysis = _analysis_cache().get(str(selected["alert_key"]))

            st.markdown(
                f"""
<div class="workspace-panel">
  <div class="workspace-title">
    <strong>Détail de la notification</strong>
    <span style="color:#78899A;font-size:.68rem;">
      ID : {html.escape(str(selected.get("article_id") or "—"))}
    </span>
  </div>
  <div class="detail-meta-grid">
    <div class="detail-meta">
      <div class="meta-label">Source</div>
      <div class="meta-value">{html.escape(_source_short(selected))}</div>
    </div>
    <div class="detail-meta">
      <div class="meta-label">Entreprise</div>
      <div class="meta-value">{html.escape(_notification_company(selected))}</div>
    </div>
    <div class="detail-meta">
      <div class="meta-label">Type</div>
      <div class="meta-value">{html.escape(_document_type(selected))}</div>
    </div>
    <div class="detail-meta">
      <div class="meta-label">Date</div>
      <div class="meta-value">{html.escape(_date(selected))}</div>
    </div>
    <div class="detail-meta">
      <div class="meta-label">Priorité</div>
      <div class="meta-value">
        <span class="priority {priority_class}">{html.escape(priority_label)}</span>
      </div>
    </div>
  </div>
</div>
                """,
                unsafe_allow_html=True,
            )

            tab_summary, tab_legal, tab_actions, tab_history = st.tabs(
                [
                    "Résumé",
                    "Détails juridiques",
                    "Actions recommandées",
                    "Historique",
                ]
            )

            with tab_summary:
                text_col, preview_col = st.columns([1.48, .72], gap="medium")

                with text_col:
                    st.markdown("#### Résumé")

                    summary = str(
                        selected.get("card_summary")
                        or selected.get("detail_text")
                        or ""
                    ).strip()

                    if len(summary) > 900:
                        summary = summary[:900] + "…"

                    st.markdown(
                        f'<div class="summary-box" dir="auto">'
                        f'{_bidi_html(summary or "Aucun résumé disponible.")}'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

                    if fields:
                        st.markdown("#### Données clés")

                        key_rows = []
                        for key in (
                            "denomination",
                            "identifiant_unique",
                            "type_publication",
                            "type_modification",
                            "capital",
                            "date_publication",
                        ):
                            value = fields.get(key)
                            if value not in (None, ""):
                                key_rows.append(
                                    {
                                        "Champ": key.replace("_", " ").title(),
                                        "Valeur": value,
                                    }
                                )

                        if key_rows:
                            key_fields = {
                                str(item["Champ"]): item["Valeur"]
                                for item in key_rows
                            }
                            st.markdown(
                                _legal_fields_html(key_fields),
                                unsafe_allow_html=True,
                            )

                with preview_col:
                    st.caption("Aperçu du PDF")
                    if pdf and hasattr(st, "pdf"):
                        try:
                            st.pdf(pdf, height=305)
                        except Exception:
                            st.caption(pdf.name)
                    elif not pdf:
                        st.info("PDF non récupéré.")

                st.markdown("#### PDF associé")

                if pdf:
                    size_kb = round(pdf.stat().st_size / 1024)
                    file_left, file_action = st.columns([2.2, 1.1])

                    with file_left:
                        st.markdown(
                            f"""
<div class="pdf-card">
  <div class="pdf-file">{html.escape(pdf.name)}</div>
  <div class="pdf-meta">{size_kb} Ko · {html.escape(_document_type(selected))}</div>
</div>
                            """,
                            unsafe_allow_html=True,
                        )

                    with file_action:
                        if st.button(
                            "Ouvrir le PDF",
                            width="stretch",
                            key="desktop_v2_open_pdf",
                        ):
                            _pdf_dialog(selected)
                else:
                    st.info(
                        "Aucun PDF local pour cette alerte. "
                        "Utilisez « Importer des PDF » puis "
                        "« Récupérer les PDF manquants »."
                    )

            with tab_legal:
                st.markdown("#### Détails juridiques")

                if fields:
                    st.markdown(
                        _legal_fields_html(fields),
                        unsafe_allow_html=True,
                    )

                detail_text = str(
                    selected.get("detail_text") or ""
                ).strip()

                if detail_text:
                    with st.expander("Texte complet", expanded=False):
                        st.write(detail_text)

            with tab_actions:
                st.markdown("#### Actions recommandées")

                if analysis:
                    st.write(
                        analysis.get("Action_Recommandée_IA")
                        or "Aucune action recommandée."
                    )
                    st.caption(
                        f"Risque {analysis.get('Score_Risque_IA', '—')} · "
                        f"Opportunité {analysis.get('Score_Opportunité_IA', '—')}"
                    )
                else:
                    st.info(
                        "Lancez l'analyse IA pour générer les scores "
                        "et l'action recommandée."
                    )

            with tab_history:
                history_df = pd.DataFrame(
                    [
                        {
                            "Événement": "Notification",
                            "Date / état": selected.get(
                                "notification_date"
                            ) or "—",
                        },
                        {
                            "Événement": "Détail LegalTech",
                            "Date / état": selected.get(
                                "detail_status"
                            ) or "—",
                        },
                        {
                            "Événement": "PDF",
                            "Date / état": selected.get(
                                "download_status"
                            ) or "—",
                        },
                        {
                            "Événement": "Run",
                            "Date / état": run.get("started_at") or "—",
                        },
                    ]
                )

                st.dataframe(
                    history_df,
                    hide_index=True,
                    width="stretch",
                )

            st.markdown("#### Actions rapides")

            action_ai, action_correction, action_validate, action_excel = st.columns(
                [1.45, 1.25, .92, 1.18],
                gap="small",
            )

            with action_ai:
                if st.button(
                    "Lancer l'analyse IA",
                    type="primary",
                    width="stretch",
                    key="desktop_v2_analyze",
                ):
                    with st.spinner("Analyse IA locale en cours…"):
                        row = _run_alert_analysis(selected)

                    _analysis_dialog(selected, row)

            with action_correction:
                if st.button(
                    "Envoyer en correction",
                    width="stretch",
                    key="desktop_v2_correction",
                ):
                    queue = st.session_state.setdefault(
                        "desktop_correction_queue",
                        [],
                    )

                    key = str(selected["alert_key"])
                    if key not in queue:
                        queue.append(key)

                    st.success("Alerte ajoutée à la file de correction.")

            with action_validate:
                if st.button(
                    "Valider",
                    width="stretch",
                    key="desktop_v2_validate",
                ):
                    validated = st.session_state.setdefault(
                        "desktop_validated",
                        set(),
                    )
                    validated.add(str(selected["alert_key"]))
                    st.success("Alerte validée pour cette session.")

            with action_excel:
                if analysis:
                    if st.button(
                        "Exporter Excel",
                        width="stretch",
                        key="desktop_v2_excel",
                    ):
                        _excel_dialog(selected, analysis)
                else:
                    st.button(
                        "Exporter Excel",
                        width="stretch",
                        disabled=True,
                        key="desktop_v2_excel_disabled",
                        help="Lancez d'abord l'analyse IA.",
                    )

    st.markdown(
        f"""
<div class="bottom-status">
  <div>
    Synchronisation : {html.escape(latest_sync)}
    &nbsp;&nbsp; · &nbsp;&nbsp;
    <span class="green-dot"></span>&nbsp; Statut : Connecté
  </div>
  <div>
    Version 1.0.0 &nbsp;&nbsp; · &nbsp;&nbsp; Environnement : Production
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div id="pdf-zone"></div>', unsafe_allow_html=True)
    st.markdown('<div id="analysis-zone"></div>', unsafe_allow_html=True)
    st.markdown('<div id="results-zone"></div>', unsafe_allow_html=True)
    st.markdown('<div id="corrections-zone"></div>', unsafe_allow_html=True)
    st.markdown('<div id="exports-zone"></div>', unsafe_allow_html=True)
    st.markdown('<div id="settings-zone"></div>', unsafe_allow_html=True)
