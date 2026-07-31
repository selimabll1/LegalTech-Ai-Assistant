from __future__ import annotations

from datetime import datetime
from pathlib import Path
import html
import math
import os
import sqlite3
from typing import Any

import pandas as pd
import streamlit as st

from config import ASSETS_DIR
from modules.excel_manager import analysis_to_row, export_results
from modules.llm_analyzer import analyze_legal_text
from modules.notifications_dashboard_section_v3 import (
    DEFAULT_DB,
    _all_alerts,
    _connect,
    _latest_run,
    _notifications,
    _pdf_path,
    _safe_json,
    _sync_missing_pdfs_headless,
    _sync_notifications_headless,
)
from modules.pdf_extractor import save_uploaded_pdf
from modules.scoring_engine import score_analysis


UGFS_DESKTOP_UI_VERSION = "ugfs_desktop_ui_preview_v1"


# ============================================================
# Visual system
# ============================================================

NAVY = "#061B2D"
NAVY_2 = "#082641"
BLUE = "#1266F1"
BLUE_2 = "#0C7DFF"
TEXT = "#13294B"
MUTED = "#6F8197"
BORDER = "#DCE6F1"
BG = "#F5F8FC"
SUCCESS = "#18B781"
WARNING = "#F6A63C"
DANGER = "#F35A5A"
PURPLE = "#8E63E9"


def _logo_path() -> Path | None:
    path = ASSETS_DIR / "ugfs_logo_clean.png"
    return path if path.exists() else None


def _inject_css() -> None:
    st.markdown(
        f"""
<style>
:root {{
  --navy: {NAVY};
  --navy2: {NAVY_2};
  --blue: {BLUE};
  --blue2: {BLUE_2};
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
  height: 0px !important;
  min-height: 0px !important;
  background: transparent !important;
}}

[data-testid="stToolbar"] {{
  display: none !important;
}}

[data-testid="stSidebar"] {{
  min-width: 238px !important;
  max-width: 238px !important;
  background:
    radial-gradient(circle at 75% 8%, rgba(22,102,241,.22), transparent 25%),
    linear-gradient(180deg, #061B2D 0%, #071E34 54%, #041525 100%);
  border-right: 1px solid rgba(255,255,255,.08);
}}

[data-testid="stSidebar"] > div:first-child {{
  padding: 0 !important;
}}

[data-testid="stSidebar"] .block-container {{
  padding: .85rem .85rem 1rem !important;
}}

[data-testid="stSidebar"] .stFileUploader {{
  margin-top: .35rem;
}}

[data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] {{
  background: rgba(255,255,255,.045) !important;
  border: 1px dashed rgba(85,167,255,.50) !important;
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
  min-height: 2.7rem !important;
  font-weight: 800 !important;
}}

.block-container {{
  padding: 1.1rem 1.2rem 1rem !important;
  max-width: none !important;
}}

.ugfs-brand {{
  display:flex;
  align-items:center;
  justify-content:center;
  padding: .35rem 0 .8rem;
}}

.ugfs-brand img {{
  width: 94px;
  filter: drop-shadow(0 10px 25px rgba(26,121,255,.30));
}}

.ugfs-sidebar-title {{
  color:white;
  font-size:.90rem;
  font-weight:800;
  text-align:center;
  margin-top:.25rem;
}}

.ugfs-side-nav {{
  display:flex;
  flex-direction:column;
  gap:.26rem;
  margin: 1rem 0 1.25rem;
}}

.ugfs-side-nav a {{
  display:flex;
  gap:.72rem;
  align-items:center;
  text-decoration:none;
  color:rgba(255,255,255,.86);
  padding:.70rem .72rem;
  border-radius:9px;
  border:1px solid transparent;
  font-weight:700;
  font-size:.89rem;
}}

.ugfs-side-nav a:hover {{
  background:rgba(255,255,255,.06);
  border-color:rgba(255,255,255,.08);
}}

.ugfs-side-nav a.active {{
  color:white;
  background:rgba(18,102,241,.15);
  border-color:#1266F1;
  box-shadow:0 8px 22px rgba(0,80,180,.17);
}}

.nav-icon {{
  width:20px;
  text-align:center;
  color:#CFE6FF;
  font-size:1rem;
}}

.nav-badge {{
  margin-left:auto;
  display:inline-flex;
  min-width:23px;
  height:23px;
  border-radius:999px;
  align-items:center;
  justify-content:center;
  background:#0D70F7;
  color:white;
  font-size:.72rem;
  font-weight:900;
}}

.sidebar-import-box {{
  border:1px solid rgba(86,170,255,.30);
  border-radius:12px;
  padding:.75rem .75rem .55rem;
  color:white;
  background:rgba(255,255,255,.03);
  margin-top:.4rem;
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
  margin:.45rem 0 .25rem;
}}

.sidebar-company {{
  margin-top:1.3rem;
  color:rgba(255,255,255,.82);
  font-size:.78rem;
  font-weight:750;
  display:flex;
  align-items:center;
  gap:.45rem;
}}

.green-dot {{
  display:inline-block;
  width:9px;
  height:9px;
  border-radius:50%;
  background:{SUCCESS};
  box-shadow:0 0 10px rgba(24,183,129,.45);
}}

.app-shell {{
  background:rgba(255,255,255,.88);
  border:1px solid #E3EBF4;
  border-radius:18px;
  box-shadow:0 15px 50px rgba(23,52,83,.08);
  padding:1.15rem 1.25rem .85rem;
}}

.app-header {{
  display:flex;
  justify-content:space-between;
  align-items:flex-start;
  gap:1rem;
  border-bottom:1px solid #E8EEF5;
  padding-bottom:1rem;
}}

.app-title {{
  color:#0B1733;
  font-size:1.73rem;
  line-height:1.1;
  font-weight:900;
  letter-spacing:-.025em;
}}

.app-subtitle {{
  color:#647993;
  margin-top:.36rem;
  font-size:.88rem;
  font-weight:600;
}}

.app-account {{
  display:flex;
  align-items:center;
  gap:.65rem;
}}

.bell {{
  position:relative;
  font-size:1.28rem;
  color:#18385E;
}}

.bell-badge {{
  position:absolute;
  right:-9px;
  top:-10px;
  background:#176CF2;
  color:white;
  border-radius:999px;
  min-width:21px;
  height:21px;
  display:flex;
  align-items:center;
  justify-content:center;
  font-size:.66rem;
  font-weight:900;
}}

.avatar {{
  width:44px;
  height:44px;
  border-radius:50%;
  display:flex;
  align-items:center;
  justify-content:center;
  border:1px solid #D8E3EF;
  color:#223553;
  font-weight:800;
  background:#FAFCFF;
}}

.status-strip {{
  background:#F7FBFF;
  border:1px solid #CFE0F5;
  border-radius:10px;
  padding:.72rem .85rem;
  margin:.75rem 0 .8rem;
  display:flex;
  justify-content:space-between;
  gap:1rem;
  font-size:.80rem;
  color:#334A67;
}}

.status-strip strong {{
  color:#152B49;
}}

.panel-title-row {{
  display:flex;
  align-items:center;
  justify-content:space-between;
  border-bottom:1px solid #E7EDF4;
  padding:.83rem .95rem .74rem;
}}

.panel-title {{
  color:#142A47;
  font-size:.86rem;
  font-weight:900;
  text-transform:uppercase;
  letter-spacing:.015em;
}}

.panel {{
  background:white;
  border:1px solid #DFE7F0;
  border-radius:12px;
  box-shadow:0 8px 24px rgba(25,55,88,.045);
  overflow:hidden;
}}

.detail-meta-grid {{
  display:grid;
  grid-template-columns:repeat(5, minmax(0,1fr));
  border-bottom:1px solid #E7EDF4;
}}

.detail-meta {{
  padding:.72rem .80rem;
  border-right:1px solid #EDF1F5;
}}

.detail-meta:last-child {{
  border-right:none;
}}

.meta-label {{
  color:#788BA1;
  font-size:.68rem;
  font-weight:700;
}}

.meta-value {{
  color:#172C48;
  font-size:.82rem;
  font-weight:850;
  margin-top:.25rem;
  overflow-wrap:anywhere;
}}

.source-dot {{
  display:inline-block;
  width:8px;
  height:8px;
  border-radius:50%;
  margin-right:.38rem;
  background:#2377FF;
}}

.priority {{
  display:inline-block;
  padding:.20rem .55rem;
  border-radius:7px;
  font-size:.68rem;
  font-weight:800;
}}

.priority.high {{
  color:#DD3D3D;
  background:#FFF0F0;
  border:1px solid #FFD2D2;
}}

.priority.medium {{
  color:#A96A00;
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

.tab-title {{
  color:#102946;
  font-weight:900;
  margin:.15rem 0 .55rem;
}}

.summary-box {{
  color:#263A54;
  font-size:.83rem;
  line-height:1.65;
}}

.pdf-card {{
  border:1px solid #E5ECF3;
  border-radius:10px;
  padding:.62rem .7rem;
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:.7rem;
  background:#FCFDFE;
}}

.pdf-file {{
  color:#283C55;
  font-size:.78rem;
  font-weight:800;
  overflow-wrap:anywhere;
}}

.pdf-meta {{
  color:#7B8DA0;
  font-size:.67rem;
  margin-top:.18rem;
}}

.bottom-status {{
  margin-top:.8rem;
  padding:.65rem .2rem .05rem;
  border-top:1px solid #E5ECF3;
  display:flex;
  justify-content:space-between;
  gap:1rem;
  color:#60748A;
  font-size:.72rem;
}}

.bottom-left {{
  display:flex;
  gap:1.5rem;
}}

.stButton > button,
.stDownloadButton > button {{
  border-radius:8px !important;
  min-height:2.75rem !important;
  font-weight:800 !important;
  border:1px solid #D6E1ED !important;
  box-shadow:none !important;
}}

.stButton > button[kind="primary"] {{
  background:linear-gradient(180deg,#1979FF,#0564E8) !important;
  color:white !important;
  border-color:#0564E8 !important;
}}

[data-testid="stTextInput"] input {{
  border-radius:8px !important;
  min-height:2.75rem;
  border:1px solid #D5E0EB !important;
  background:white !important;
}}

[data-testid="stDataFrame"] {{
  border:0 !important;
}}

div[data-testid="stTabs"] button[role="tab"] {{
  font-size:.77rem;
  font-weight:800;
  color:#536A84;
}}

div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {{
  color:#1266F1;
}}

div[data-testid="stDialog"] > div {{
  border-radius:16px !important;
}}

.small-note {{
  color:#72849A;
  font-size:.72rem;
}}

@media(max-width:1200px) {{
  [data-testid="stSidebar"] {{
    min-width:210px !important;
    max-width:210px !important;
  }}
  .detail-meta-grid {{
    grid-template-columns:1fr 1fr;
  }}
}}
</style>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# DB / model helpers
# ============================================================

def _load_state(db_path: Path = DEFAULT_DB):
    con = _connect(db_path)
    try:
        run = _latest_run(con)
        if not run:
            return None, [], []

        notifications = _notifications(con, run["run_id"])
        alerts = _all_alerts(con, run["run_id"])

        for alert in alerts:
            alert["source_fields"] = _safe_json(
                alert.get("source_fields_json")
            )

        return run, notifications, alerts
    finally:
        con.close()


def _source_name(alert: dict[str, Any]) -> str:
    return str(
        alert.get("source_label")
        or alert.get("source")
        or "LegalTech"
    )


def _document_type(alert: dict[str, Any]) -> str:
    fields = alert.get("source_fields") or {}

    for key in (
        "type_modification",
        "type_publication",
        "type_reservation",
        "categorie_registre",
    ):
        value = fields.get(key)
        if value:
            return str(value)

    source = str(alert.get("source") or "").casefold()
    label = _source_name(alert).casefold()

    if source == "rne" or "registre national" in label:
        return "RNE"
    if source == "jort" or "journal officiel" in label:
        return "JORT"
    if source.startswith("jr") or label.startswith("journal"):
        return "Presse"
    return "Alerte"


def _date(alert: dict[str, Any]) -> str:
    raw = str(alert.get("card_date") or "").strip()
    if "T" in raw:
        raw = raw.split("T", 1)[0]
    return raw or "—"


def _notification_company(alert: dict[str, Any]) -> str:
    return str(
        alert.get("company_or_query")
        or alert.get("notification_company")
        or "—"
    )


def _analysis_cache() -> dict[str, dict[str, Any]]:
    return st.session_state.setdefault("desktop_alert_analysis", {})


def _priority_for(alert: dict[str, Any]) -> tuple[str, str]:
    analysis = _analysis_cache().get(str(alert.get("alert_key")))
    if not analysis:
        return "À analyser", "none"

    score = int(analysis.get("Score_Risque_IA", 0) or 0)
    if score >= 60:
        return "Élevée", "high"
    if score >= 30:
        return "Moyenne", "medium"
    return "Faible", "low"


def _analysis_text(alert: dict[str, Any]) -> str:
    return str(
        alert.get("detail_text")
        or alert.get("card_summary")
        or alert.get("card_text")
        or ""
    ).strip()


def _run_alert_analysis(alert: dict[str, Any]) -> dict[str, Any]:
    source_text = _analysis_text(alert)
    if not source_text:
        raise ValueError(
            "Aucun texte exploitable n'est disponible pour cette alerte."
        )

    analysis = analyze_legal_text(
        source_text,
        ocr_quality=1.0,
    )
    analysis = score_analysis(analysis, source_text)

    pdf = _pdf_path(alert)
    document_name = (
        pdf.name
        if pdf is not None
        else str(alert.get("card_title") or "Alerte LegalTech")
    )

    row = analysis_to_row(
        analysis,
        document_name,
        1,
    )

    row.update(
        {
            "Référence_Annonce": alert.get("article_id") or "",
            "Source_LegalTech": _source_name(alert),
            "Notification_LegalTech": _notification_company(alert),
            "Date_Notification_LegalTech": alert.get("notification_date") or "",
            "Date_Alerte_LegalTech": _date(alert),
            "Extrait_Source": source_text[:500],
        }
    )

    _analysis_cache()[str(alert["alert_key"])] = row
    return row


def _matches_query(alert: dict[str, Any], query: str) -> bool:
    if not query:
        return True

    fields = alert.get("source_fields") or {}
    blob = " ".join(
        [
            _source_name(alert),
            _notification_company(alert),
            _document_type(alert),
            _date(alert),
            str(alert.get("card_title") or ""),
            str(alert.get("card_summary") or ""),
            str(alert.get("detail_text") or ""),
            str(alert.get("article_id") or ""),
            str(alert.get("doc_id") or ""),
            " ".join(str(v) for v in fields.values()),
        ]
    ).casefold()

    return query.casefold() in blob


# ============================================================
# Sidebar
# ============================================================

def _render_sidebar(notification_count: int) -> None:
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
        else:
            st.markdown(
                "<div class='ugfs-sidebar-title'>UGFS NORTH AFRICA</div>",
                unsafe_allow_html=True,
            )

        st.markdown(
            """
<div class="ugfs-side-nav">
  <a href="#home"><span class="nav-icon">⌂</span>Accueil</a>
  <a class="active" href="#notifications">
    <span class="nav-icon">♧</span>Notifications
    <span class="nav-badge">__COUNT__</span>
  </a>
  <a href="#pdf-zone"><span class="nav-icon">▤</span>Documents PDF</a>
  <a href="#analysis-zone"><span class="nav-icon">✦</span>Analyse IA</a>
  <a href="#results-zone"><span class="nav-icon">▦</span>Résultats</a>
  <a href="#corrections-zone"><span class="nav-icon">✓</span>Corrections</a>
  <a href="#exports-zone"><span class="nav-icon">⇩</span>Exports</a>
  <a href="#settings-zone"><span class="nav-icon">⚙</span>Paramètres</a>
</div>
            """.replace("__COUNT__", str(notification_count)),
            unsafe_allow_html=True,
        )

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
            key="desktop_sidebar_upload",
        )

        if uploaded:
            if st.button(
                "Sélectionner / enregistrer",
                width="stretch",
                key="desktop_sidebar_save",
            ):
                saved = 0
                for file in uploaded:
                    save_uploaded_pdf(file)
                    saved += 1
                st.success(f"{saved} PDF enregistré(s).")

        st.markdown(
            """
<div class="sidebar-company">
  <span class="green-dot"></span>
  UGFS North Africa
</div>
            """,
            unsafe_allow_html=True,
        )


def _to_b64(path: Path) -> str:
    import base64
    return base64.b64encode(path.read_bytes()).decode("ascii")


# ============================================================
# Dialogs
# ============================================================

def _analysis_body(alert: dict[str, Any], row: dict[str, Any]) -> None:
    st.markdown(f"### Analyse IA — {_notification_company(alert)}")
    st.caption(
        f"{_source_name(alert)} · {_date(alert)} · "
        f"{alert.get('card_title') or ''}"
    )

    risk = row.get("Score_Risque_IA", "—")
    risk_level = row.get("Niveau_Risque_IA", "—")
    opp = row.get("Score_Opportunité_IA", "—")
    opp_level = row.get("Niveau_Opportunité_IA", "—")
    confidence = row.get("Confiance_IA", "—")

    c1, c2, c3 = st.columns(3)
    c1.metric("Risque", risk, risk_level)
    c2.metric("Opportunité", opp, opp_level)
    c3.metric("Confiance", confidence)

    st.markdown("#### Événement détecté")
    st.write(row.get("Type_Événement_IA", "—"))

    st.markdown("#### Résumé IA")
    st.write(row.get("Résumé_IA", "—"))

    left, right = st.columns(2)
    with left:
        st.markdown("#### Risques identifiés")
        risks = str(row.get("Risques_Détectés_IA", "") or "").strip()
        st.write(risks or "Aucun risque explicite détecté.")

        derived = str(
            row.get("Évaluation_Risque_Dérivée", "") or ""
        ).strip()
        if derived:
            st.warning(derived)

    with right:
        st.markdown("#### Opportunités")
        opportunities = str(
            row.get("Opportunités_Détectées_IA", "") or ""
        ).strip()
        st.write(opportunities or "Aucune opportunité directe détectée.")

        derived_opp = str(
            row.get("Opportunité_Potentielle_Dérivée", "") or ""
        ).strip()
        if derived_opp:
            st.success(derived_opp)

    st.markdown("#### Action recommandée")
    st.write(row.get("Action_Recommandée_IA", "—"))

    with st.expander("Justification & traçabilité", expanded=False):
        st.write("**Détail score risque**")
        st.text(str(row.get("Détail_Score_Risque", "") or "—"))

        st.write("**Détail score opportunité**")
        st.text(str(row.get("Détail_Score_Opportunité", "") or "—"))

        st.write("**Validation factuelle**")
        st.write(row.get("Statut_Validation_Factuelle", "—"))


def _excel_preview_body(alert: dict[str, Any], row: dict[str, Any]) -> None:
    st.markdown("### Prévisualisation Excel")

    preview_columns = [
        "Société",
        "Catégorie",
        "Type_Événement_IA",
        "Score_Risque_IA",
        "Niveau_Risque_IA",
        "Score_Opportunité_IA",
        "Niveau_Opportunité_IA",
        "Confiance_IA",
        "Action_Recommandée_IA",
    ]

    preview = {
        key: row.get(key, "")
        for key in preview_columns
    }

    st.dataframe(
        pd.DataFrame([preview]),
        hide_index=True,
        width="stretch",
    )

    with st.expander("Voir toutes les colonnes exportables"):
        st.dataframe(
            pd.DataFrame([row]),
            hide_index=True,
            width="stretch",
        )

    if st.button(
        "Générer le fichier Excel",
        type="primary",
        width="stretch",
        key="desktop_generate_excel",
    ):
        path = export_results([row])
        st.session_state["desktop_last_excel"] = str(path)

    last = st.session_state.get("desktop_last_excel")
    if last and Path(last).exists():
        path = Path(last)
        st.download_button(
            "Télécharger l'Excel",
            data=path.read_bytes(),
            file_name=path.name,
            mime=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
            width="stretch",
            key="desktop_excel_download",
        )


def _pdf_dialog_body(alert: dict[str, Any]) -> None:
    pdf = _pdf_path(alert)
    st.markdown(f"### {alert.get('card_title') or 'PDF LegalTech'}")
    st.caption(
        f"{_source_name(alert)} · {_document_type(alert)} · {_date(alert)}"
    )

    if pdf is None:
        st.info("Aucun PDF local n'est disponible pour cette alerte.")
        return

    if hasattr(st, "pdf"):
        st.pdf(pdf, height=680)

    st.download_button(
        "Télécharger le PDF",
        data=pdf.read_bytes(),
        file_name=pdf.name,
        mime="application/pdf",
        width="stretch",
        key="desktop_pdf_download",
    )


if hasattr(st, "dialog"):
    @st.dialog("Analyse IA", width="large")
    def _analysis_dialog(alert, row):
        _analysis_body(alert, row)

    @st.dialog("Export Excel", width="large")
    def _excel_dialog(alert, row):
        _excel_preview_body(alert, row)

    @st.dialog("Document PDF", width="large")
    def _pdf_dialog(alert):
        _pdf_dialog_body(alert)
else:
    def _analysis_dialog(alert, row):
        _analysis_body(alert, row)

    def _excel_dialog(alert, row):
        _excel_preview_body(alert, row)

    def _pdf_dialog(alert):
        _pdf_dialog_body(alert)


# ============================================================
# Main desktop workspace
# ============================================================

def render_ugfs_desktop_app() -> None:
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

    _render_sidebar(len(notifications))

    st.markdown('<div id="home"></div>', unsafe_allow_html=True)

    new_items = st.session_state.get("desktop_new_notifications", [])
    new_count = len(new_items)

    st.markdown(
        f"""
<div class="app-shell">
  <div class="app-header">
    <div>
      <div class="app-title">Système de Veille LegalTech</div>
      <div class="app-subtitle">
        Notifications LegalTech &nbsp;•&nbsp; PDF &nbsp;•&nbsp; OCR
        &nbsp;•&nbsp; Analyse IA &nbsp;•&nbsp; Export Excel
      </div>
    </div>
    <div class="app-account">
      <div class="bell">♧<span class="bell-badge">{new_count}</span></div>
      <div class="avatar">AD</div>
      <div style="color:#45617F;font-size:1rem;">⌄</div>
    </div>
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div id="notifications"></div>', unsafe_allow_html=True)

    # -------------------- action/search row --------------------
    search_col, filter_col, period_col, priority_col, sync_col, import_col = st.columns(
        [3.2, 1.05, 1.15, 1.05, 1.25, 1.55],
        gap="small",
    )

    with search_col:
        query = st.text_input(
            "Rechercher",
            placeholder="Rechercher (source, entreprise, identifiant…)",
            label_visibility="collapsed",
            key="desktop_search",
        )

    source_options = sorted({_source_name(a) for a in alerts})
    type_options = sorted({_document_type(a) for a in alerts})

    with filter_col:
        with st.popover("☷  Filtres", width="stretch"):
            selected_sources = st.multiselect(
                "Source",
                source_options,
                key="desktop_filter_source",
            )
            selected_types = st.multiselect(
                "Type",
                type_options,
                key="desktop_filter_type",
            )

    with period_col:
        with st.popover("▣  Période", width="stretch"):
            st.caption(
                "Filtre de date simplifié pour cette première version UI."
            )
            date_filter = st.text_input(
                "Contient",
                placeholder="ex. 2026-07",
                key="desktop_date_filter",
            )

    with priority_col:
        with st.popover("⚑  Priorité", width="stretch"):
            priority_filter = st.multiselect(
                "Priorité",
                ["Élevée", "Moyenne", "Faible", "À analyser"],
                key="desktop_priority_filter",
            )

    with sync_col:
        if st.button(
            "⟳  Synchroniser",
            width="stretch",
            key="desktop_sync",
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

            st.session_state["desktop_sync_log"] = log
            if ok:
                new_run, new_notifications, _ = _load_state()
                after = {
                    (
                        str(n.get("company_or_query") or "").casefold(),
                        str(n.get("notification_date") or ""),
                    )
                    for n in new_notifications
                }
                delta = after - before
                st.session_state["desktop_new_notifications"] = list(delta)
                st.rerun()
            else:
                st.error("La synchronisation a échoué.")
                with st.expander("Journal"):
                    st.code(log or "Aucun journal.")

    with import_col:
        with st.popover("⇩  Importer des PDF", width="stretch"):
            top_upload = st.file_uploader(
                "PDF",
                type=["pdf"],
                accept_multiple_files=True,
                key="desktop_top_upload",
            )
            if top_upload and st.button(
                "Enregistrer",
                width="stretch",
                key="desktop_top_save",
            ):
                for file in top_upload:
                    save_uploaded_pdf(file)
                st.success(f"{len(top_upload)} PDF enregistré(s).")

            if st.button(
                "Récupérer les PDF manquants",
                width="stretch",
                key="desktop_missing_pdfs",
            ):
                with st.spinner("Récupération des PDF manquants…"):
                    ok, log = _sync_missing_pdfs_headless()
                if ok:
                    st.success("Récupération PDF terminée.")
                    st.rerun()
                else:
                    st.error("La récupération PDF a échoué.")
                    with st.expander("Journal PDF"):
                        st.code(log or "Aucun journal.")

    latest_sync = str(run.get("started_at") or "—")
    st.markdown(
        f"""
<div class="status-strip">
  <div>✓ &nbsp; <strong>Dernière synchronisation :</strong> {html.escape(latest_sync)}</div>
  <div><span class="green-dot"></span> &nbsp; {new_count} nouvelle(s) notification(s)</div>
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

        if date_filter and date_filter.casefold() not in _date(alert).casefold():
            continue

        priority_label, _ = _priority_for(alert)
        if priority_filter and priority_label not in priority_filter:
            continue

        filtered.append(alert)

    # -------------------- two-pane layout --------------------
    list_col, detail_col = st.columns([1.06, 1.0], gap="small")

    selected_key = st.session_state.get("desktop_selected_alert")

    with list_col:
        st.markdown(
            f"""
<div class="panel">
  <div class="panel-title-row">
    <div class="panel-title">Liste des notifications ({len(filtered)})</div>
    <div style="color:#46647F;">⟳</div>
  </div>
</div>
            """,
            unsafe_allow_html=True,
        )

        page_size = 10
        total_pages = max(1, math.ceil(len(filtered) / page_size))
        current_page = int(st.session_state.get("desktop_page", 1))
        current_page = min(max(1, current_page), total_pages)

        start = (current_page - 1) * page_size
        page_alerts = filtered[start:start + page_size]

        rows = []
        for alert in page_alerts:
            priority_label, _ = _priority_for(alert)
            pdf = _pdf_path(alert)
            rows.append(
                {
                    "Source": _source_name(alert),
                    "Entreprise": _notification_company(alert),
                    "Type": _document_type(alert),
                    "Date": _date(alert),
                    "PDF": "✓" if pdf else "—",
                    "Priorité": priority_label,
                }
            )

        table_df = pd.DataFrame(rows)

        if not table_df.empty:
            event = st.dataframe(
                table_df,
                hide_index=True,
                width="stretch",
                height=390,
                key="desktop_alert_table",
                on_select="rerun",
                selection_mode="single-row",
            )

            selected_rows = list(
                getattr(getattr(event, "selection", None), "rows", [])
                or []
            )

            if selected_rows:
                selected_index = selected_rows[0]
                if 0 <= selected_index < len(page_alerts):
                    selected_key = page_alerts[selected_index]["alert_key"]
                    st.session_state["desktop_selected_alert"] = selected_key

        pager_left, pager_mid, pager_right = st.columns([1.1, 1.8, 1.1])
        with pager_left:
            if st.button(
                "‹",
                disabled=current_page <= 1,
                width="stretch",
                key="desktop_prev",
            ):
                st.session_state["desktop_page"] = current_page - 1
                st.rerun()

        with pager_mid:
            st.caption(
                f"Affichage {start + 1 if filtered else 0} à "
                f"{min(start + page_size, len(filtered))} sur {len(filtered)}"
                f" · Page {current_page}/{total_pages}"
            )

        with pager_right:
            if st.button(
                "›",
                disabled=current_page >= total_pages,
                width="stretch",
                key="desktop_next",
            ):
                st.session_state["desktop_page"] = current_page + 1
                st.rerun()

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
        st.session_state["desktop_selected_alert"] = selected["alert_key"]

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
<div class="panel">
  <div class="panel-title-row">
    <div class="panel-title">Détail de la notification</div>
    <div style="color:#687D92;font-size:.72rem;">
      ID : {html.escape(str(selected.get("article_id") or "—"))}
    </div>
  </div>
  <div class="detail-meta-grid">
    <div class="detail-meta">
      <div class="meta-label">Source</div>
      <div class="meta-value"><span class="source-dot"></span>{html.escape(_source_name(selected))}</div>
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
      <div class="meta-value"><span class="priority {priority_class}">{html.escape(priority_label)}</span></div>
    </div>
  </div>
</div>
                """,
                unsafe_allow_html=True,
            )

            tab_summary, tab_legal, tab_actions, tab_history = st.tabs(
                [
                    "▦  Résumé",
                    "▧  Détails juridiques",
                    "⚠  Actions recommandées",
                    "◷  Historique",
                ]
            )

            with tab_summary:
                text_col, preview_col = st.columns([1.45, .75], gap="medium")

                with text_col:
                    st.markdown(
                        "<div class='tab-title'>Résumé</div>",
                        unsafe_allow_html=True,
                    )

                    summary = str(
                        selected.get("card_summary")
                        or selected.get("detail_text")
                        or ""
                    ).strip()

                    if len(summary) > 900:
                        summary = summary[:900] + "…"

                    st.markdown(
                        f"<div class='summary-box'>{html.escape(summary or 'Aucun résumé disponible.')}</div>",
                        unsafe_allow_html=True,
                    )

                    if fields:
                        st.markdown("##### Données clés")
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
                            st.dataframe(
                                pd.DataFrame(key_rows),
                                hide_index=True,
                                width="stretch",
                            )

                with preview_col:
                    if pdf:
                        st.caption("Aperçu du PDF")
                        if hasattr(st, "pdf"):
                            try:
                                st.pdf(pdf, height=320)
                            except Exception:
                                st.caption(pdf.name)
                    else:
                        st.info("PDF non récupéré.")

                st.markdown("##### PDF associé")
                if pdf:
                    size_kb = round(pdf.stat().st_size / 1024)
                    file_left, file_actions = st.columns([2.2, 1.3])
                    with file_left:
                        st.markdown(
                            f"""
<div class="pdf-card">
  <div>
    <div class="pdf-file">PDF · {html.escape(pdf.name)}</div>
    <div class="pdf-meta">{size_kb} Ko · {_document_type(selected)}</div>
  </div>
</div>
                            """,
                            unsafe_allow_html=True,
                        )
                    with file_actions:
                        if st.button(
                            "Ouvrir le PDF",
                            width="stretch",
                            key="desktop_open_pdf",
                        ):
                            _pdf_dialog(selected)
                else:
                    st.info(
                        "Aucun PDF local. Utilisez « Importer des PDF » "
                        "→ « Récupérer les PDF manquants »."
                    )

            with tab_legal:
                st.markdown("#### Détails juridiques")

                if fields:
                    legal_rows = [
                        {
                            "Champ": key.replace("_", " ").title(),
                            "Valeur": value,
                        }
                        for key, value in fields.items()
                        if value not in (None, "")
                    ]
                    st.dataframe(
                        pd.DataFrame(legal_rows),
                        hide_index=True,
                        width="stretch",
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
                st.markdown("#### Historique")
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

            st.markdown("##### Actions rapides")
            action_ai, action_correction, action_validate, action_excel = st.columns(
                [1.35, 1.3, 1.0, 1.25],
                gap="small",
            )

            with action_ai:
                if st.button(
                    "✦  Lancer l'analyse IA",
                    type="primary",
                    width="stretch",
                    key="desktop_analyze",
                ):
                    with st.spinner("Analyse IA locale en cours…"):
                        row = _run_alert_analysis(selected)

                    st.session_state["desktop_analysis_modal"] = str(
                        selected["alert_key"]
                    )
                    _analysis_dialog(selected, row)

            with action_correction:
                if st.button(
                    "⌕  Envoyer en correction",
                    width="stretch",
                    key="desktop_correction",
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
                    "✓  Valider",
                    width="stretch",
                    key="desktop_validate",
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
                        "▦  Exporter Excel",
                        width="stretch",
                        key="desktop_excel",
                    ):
                        _excel_dialog(selected, analysis)
                else:
                    st.button(
                        "▦  Exporter Excel",
                        width="stretch",
                        disabled=True,
                        key="desktop_excel_disabled",
                        help="Lancez d'abord l'analyse IA.",
                    )

    st.markdown(
        f"""
<div class="bottom-status">
  <div class="bottom-left">
    <span>⟳ &nbsp; Synchronisation : {html.escape(latest_sync)}</span>
    <span><span class="green-dot"></span> &nbsp; Statut : Connecté</span>
  </div>
  <div>
    Version 1.0.0 &nbsp;&nbsp; | &nbsp;&nbsp; Environnement : Production
    &nbsp; <span class="green-dot"></span>
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div id="analysis-zone"></div>', unsafe_allow_html=True)
    st.markdown('<div id="results-zone"></div>', unsafe_allow_html=True)
    st.markdown('<div id="corrections-zone"></div>', unsafe_allow_html=True)
    st.markdown('<div id="exports-zone"></div>', unsafe_allow_html=True)
    st.markdown('<div id="settings-zone"></div>', unsafe_allow_html=True)
    st.markdown('<div id="pdf-zone"></div>', unsafe_allow_html=True)
