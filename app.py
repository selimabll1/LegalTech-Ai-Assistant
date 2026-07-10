import base64
from pathlib import Path

import pandas as pd
import streamlit as st

from config import ASSETS_DIR, OLLAMA_MODEL
from modules.excel_manager import analysis_to_row, export_results, read_corrected_excel
from modules.feedback_manager import (
    append_training_dataset,
    load_feedback_memory,
    update_memory_from_excel,
)
from modules.llm_analyzer import analyze_legal_text
from modules.ocr_engine import extract_pdf_text
from modules.pdf_extractor import list_pdf_files, save_uploaded_pdf
from modules.scoring_engine import score_analysis


st.set_page_config(
    page_title="UGFS-NA LegalTech AI Assistant",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# Branding / constants
# ============================================================

def find_logo() -> Path | None:
    logo_path = ASSETS_DIR / "ugfs_logo_clean.png"
    if logo_path.exists():
        return logo_path
    return None


LOGO = find_logo()

UGFS_BLUE = "#0B5D86"
UGFS_NAVY = "#13294B"
UGFS_DARK = "#061B2D"
UGFS_DARK_2 = "#0A263B"
UGFS_ACCENT = "#1B78A8"
UGFS_CYAN = "#35B7E6"
UGFS_BG = "#F4F8FB"
UGFS_BORDER = "#D6E2EE"
TEXT_DARK = "#18314F"
TEXT_MUTED = "#71839A"
SUCCESS_BG = "#EFF8F3"
WARNING_BG = "#FFF8E8"
ERROR_BG = "#FFF1F0"


def image_to_base64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("utf-8")


# ============================================================
# CSS
# ============================================================

def inject_css():
    st.markdown(
        f"""
        <style>
        :root {{
            --ugfs-blue: {UGFS_BLUE};
            --ugfs-navy: {UGFS_NAVY};
            --ugfs-dark: {UGFS_DARK};
            --ugfs-dark-2: {UGFS_DARK_2};
            --ugfs-accent: {UGFS_ACCENT};
            --ugfs-cyan: {UGFS_CYAN};
            --ugfs-bg: {UGFS_BG};
            --ugfs-border: {UGFS_BORDER};
            --text-dark: {TEXT_DARK};
            --text-muted: {TEXT_MUTED};
        }}

        .stApp {{
            background:
                radial-gradient(circle at top right, rgba(27,120,168,0.07), transparent 24%),
                linear-gradient(180deg, #FBFDFF 0%, var(--ugfs-bg) 100%);
            color: var(--text-dark);
        }}

        .block-container {{
            padding-top: 1.15rem;
            padding-bottom: 2.4rem;
            max-width: 1600px;
        }}

        header[data-testid="stHeader"] {{
            background: rgba(255,255,255,0.65);
            backdrop-filter: blur(10px);
        }}

        /* ================= SIDEBAR ================= */

        [data-testid="stSidebar"] {{
            background:
                radial-gradient(circle at 32% 4%, rgba(53,183,230,0.22), transparent 26%),
                linear-gradient(180deg, #061B2D 0%, #081F35 45%, #041423 100%);
            border-right: 1px solid rgba(255,255,255,0.08);
            box-shadow: 18px 0 45px rgba(6,27,45,0.18);
        }}

        [data-testid="stSidebar"] .block-container {{
            padding: 1rem 0.85rem 1.2rem 0.85rem;
        }}

        .sidebar-brand {{
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 0.35rem 0 0.8rem 0;
            margin-bottom: 0.25rem;
        }}

        .sidebar-logo {{
            width: 116px;
            max-width: 78%;
            margin: 0 auto;
            display: block;
            filter: drop-shadow(0 18px 25px rgba(53,183,230,0.26));
            animation: floatLogo 4s ease-in-out infinite;
        }}

        @keyframes floatLogo {{
            0% {{ transform: translateY(0px); }}
            50% {{ transform: translateY(-4px); }}
            100% {{ transform: translateY(0px); }}
        }}

        .brand-fallback {{
            width: 112px;
            height: 112px;
            border-radius: 30px;
            display: flex;
            align-items: center;
            justify-content: center;
            background: linear-gradient(135deg, rgba(53,183,230,0.95), rgba(11,93,134,0.95));
            color: white;
            font-size: 1.55rem;
            font-weight: 800;
            letter-spacing: -0.06em;
            box-shadow: 0 18px 35px rgba(53,183,230,0.22);
        }}

        .sidebar-app-title {{
            margin-top: 0.75rem;
            color: rgba(255,255,255,0.94);
            font-weight: 800;
            text-align: center;
            font-size: 0.98rem;
            line-height: 1.25;
        }}

        .sidebar-subtitle {{
            margin-top: 0.22rem;
            color: rgba(255,255,255,0.55);
            text-align: center;
            font-size: 0.78rem;
        }}

        .side-divider {{
            height: 1px;
            background: linear-gradient(90deg, transparent, rgba(255,255,255,0.18), transparent);
            margin: 0.7rem 0 1rem 0;
        }}

        .sidebar-section-label {{
            font-size: 0.68rem;
            font-weight: 800;
            color: rgba(255,255,255,0.42);
            letter-spacing: 0.14em;
            text-transform: uppercase;
            margin: 0.25rem 0 0.65rem 0.35rem;
        }}

        .side-nav {{
            display: flex;
            flex-direction: column;
            gap: 0.55rem;
            margin-bottom: 1rem;
        }}

        .side-nav a {{
            position: relative;
            text-decoration: none;
            color: rgba(255,255,255,0.76);
            background: rgba(255,255,255,0.055);
            border: 1px solid rgba(255,255,255,0.075);
            border-radius: 18px;
            padding: 0.82rem 0.9rem 0.82rem 1rem;
            font-size: 0.92rem;
            font-weight: 700;
            transition: all .20s ease;
            box-shadow: 0 10px 22px rgba(0,0,0,0.12);
            backdrop-filter: blur(10px);
        }}

        .side-nav a:before {{
            content: "";
            width: 7px;
            height: 7px;
            border-radius: 50%;
            background: rgba(53,183,230,0.78);
            display: inline-block;
            margin-right: 0.65rem;
            box-shadow: 0 0 12px rgba(53,183,230,0.55);
        }}

        .side-nav a:hover {{
            transform: translateX(4px);
            color: white;
            background: linear-gradient(135deg, rgba(53,183,230,0.22), rgba(255,255,255,0.07));
            border-color: rgba(53,183,230,0.34);
            box-shadow: 0 16px 28px rgba(0,0,0,0.20);
        }}

        [data-testid="stSidebar"] [data-testid="stFileUploader"] {{
            background: transparent !important;
            border: none !important;
            padding: 0 !important;
        }}

        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] {{
            background: rgba(255,255,255,0.075) !important;
            border: 1px dashed rgba(53,183,230,0.45) !important;
            border-radius: 18px !important;
            min-height: 112px !important;
            padding: 0.8rem !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
        }}

        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] * {{
            color: rgba(255,255,255,0.82) !important;
        }}

        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] button {{
            background: linear-gradient(135deg, rgba(53,183,230,0.95), rgba(11,93,134,0.95)) !important;
            color: white !important;
            border: 0 !important;
            border-radius: 14px !important;
            min-height: 2.65rem !important;
            font-weight: 800 !important;
            box-shadow: 0 12px 22px rgba(53,183,230,0.18) !important;
        }}

        [data-testid="stSidebar"] small {{
            color: rgba(255,255,255,0.52) !important;
        }}

        [data-testid="stSidebar"] .stButton > button {{
            background: linear-gradient(135deg, rgba(53,183,230,0.95), rgba(11,93,134,0.95)) !important;
            color: white !important;
            border: 0 !important;
            box-shadow: 0 16px 25px rgba(53,183,230,0.20) !important;
            border-radius: 18px !important;
            min-height: 3.25rem !important;
        }}

        .sidebar-mini-status {{
            margin-top: 1rem;
            padding: 0.85rem;
            border-radius: 18px;
            background: rgba(255,255,255,0.055);
            border: 1px solid rgba(255,255,255,0.08);
            color: rgba(255,255,255,0.70);
            font-size: 0.78rem;
            line-height: 1.5;
        }}

        .sidebar-mini-status strong {{
            color: white;
            font-size: 0.83rem;
        }}

        /* ================= MAIN ================= */

        .topbar {{
            background:
                radial-gradient(circle at 92% 15%, rgba(53,183,230,0.18), transparent 24%),
                linear-gradient(135deg, rgba(11,93,134,0.98) 0%, rgba(19,41,75,0.98) 100%);
            border-radius: 26px;
            padding: 1.55rem 1.7rem;
            box-shadow: 0 18px 40px rgba(19,41,75,0.16);
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 1rem;
            margin-bottom: 1rem;
            animation: fadeUp .45s ease-out;
        }}

        @keyframes fadeUp {{
            from {{
                opacity: 0;
                transform: translateY(10px);
            }}
            to {{
                opacity: 1;
                transform: translateY(0);
            }}
        }}

        .topbar-left h1 {{
            margin: 0;
            color: white;
            font-size: 2.18rem;
            font-weight: 800;
            letter-spacing: -0.03em;
        }}

        .topbar-left p {{
            margin: 0.35rem 0 0 0;
            color: rgba(255,255,255,0.76);
            font-size: 0.95rem;
            font-weight: 500;
        }}

        .topbar-status {{
            display: inline-flex;
            align-items: center;
            gap: 0.55rem;
            background: rgba(255,255,255,0.14);
            color: white;
            border: 1px solid rgba(255,255,255,0.16);
            border-radius: 999px;
            padding: 0.75rem 1rem;
            font-size: 0.9rem;
            font-weight: 700;
            white-space: nowrap;
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.10);
        }}

        .section-nav {{
            display: flex;
            flex-wrap: wrap;
            gap: 0.65rem;
            margin: 0.4rem 0 1rem 0;
        }}

        .section-nav a {{
            text-decoration: none;
            color: var(--ugfs-navy);
            background: rgba(255,255,255,0.92);
            border: 1px solid var(--ugfs-border);
            border-radius: 999px;
            padding: 0.67rem 1.05rem;
            font-size: 0.88rem;
            font-weight: 700;
            transition: all .18s ease;
            box-shadow: 0 8px 18px rgba(19,41,75,0.035);
        }}

        .section-nav a:hover {{
            color: white;
            background: linear-gradient(135deg, var(--ugfs-blue), var(--ugfs-navy));
            border-color: transparent;
            transform: translateY(-1px);
        }}

        .metric-grid {{
            display: grid;
            grid-template-columns: repeat(4, minmax(0,1fr));
            gap: 0.9rem;
            margin: 0.7rem 0 1.1rem 0;
        }}

        .metric-card {{
            background: rgba(255,255,255,0.94);
            border: 1px solid var(--ugfs-border);
            border-radius: 20px;
            padding: 1.05rem;
            box-shadow: 0 10px 26px rgba(19,41,75,0.055);
            transition: all .18s ease;
        }}

        .metric-card:hover {{
            transform: translateY(-2px);
            box-shadow: 0 16px 30px rgba(19,41,75,0.08);
            border-color: rgba(11,93,134,0.22);
        }}

        .metric-label {{
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.06em;
            font-size: 0.76rem;
            font-weight: 800;
        }}

        .metric-value {{
            margin-top: 0.45rem;
            color: var(--ugfs-navy);
            font-size: 1.85rem;
            font-weight: 800;
            line-height: 1.15;
        }}

        .metric-sub {{
            margin-top: 0.35rem;
            color: var(--text-muted);
            font-size: 0.9rem;
        }}

        .section-title {{
            color: var(--ugfs-navy);
            font-size: 1.18rem;
            font-weight: 800;
            margin: 1.1rem 0 0.7rem 0;
        }}

        .panel {{
            background: rgba(255,255,255,0.92);
            border: 1px solid var(--ugfs-border);
            border-radius: 22px;
            padding: 1rem;
            box-shadow: 0 12px 28px rgba(19,41,75,0.055);
        }}

        .workflow-panel {{
            background:
                radial-gradient(circle at 97% 3%, rgba(53,183,230,0.13), transparent 24%),
                rgba(255,255,255,0.94);
            border: 1px solid var(--ugfs-border);
            border-radius: 24px;
            padding: 1.15rem;
            box-shadow: 0 14px 30px rgba(19,41,75,0.06);
            margin-bottom: 0.65rem;
        }}

        .workflow-title {{
            color: var(--ugfs-navy);
            font-size: 1.02rem;
            font-weight: 850;
            margin-bottom: 0.25rem;
        }}

        .workflow-sub {{
            color: var(--text-muted);
            font-size: 0.88rem;
            margin-bottom: 0.85rem;
        }}

        .hint-line {{
            color: var(--text-muted);
            font-size: 0.86rem;
            margin-top: 0.7rem;
            line-height: 1.45;
        }}

        .doc-list {{
            display: grid;
            grid-template-columns: 1.6fr 0.45fr 0.75fr;
            gap: 0.65rem;
            align-items: center;
            padding: 0.7rem 0.85rem;
            border-bottom: 1px solid #E6EEF6;
            font-size: 0.92rem;
        }}

        .doc-list.header {{
            color: var(--text-muted);
            text-transform: uppercase;
            font-size: 0.72rem;
            font-weight: 850;
            letter-spacing: 0.06em;
            background: #F7FBFE;
            border-radius: 14px;
            border-bottom: none;
            margin-bottom: 0.25rem;
        }}

        .doc-status {{
            display: inline-flex;
            width: fit-content;
            padding: 0.32rem 0.62rem;
            border-radius: 999px;
            background: #EAF3F8;
            color: var(--ugfs-blue);
            font-weight: 800;
            font-size: 0.78rem;
        }}

        .score-grid {{
            display: grid;
            grid-template-columns: repeat(3, minmax(0,1fr));
            gap: 0.85rem;
            margin-top: 0.2rem;
        }}

        .score-card {{
            background:
                radial-gradient(circle at 92% 12%, rgba(53,183,230,0.10), transparent 30%),
                linear-gradient(180deg, #FFFFFF 0%, #F7FBFE 100%);
            border: 1px solid var(--ugfs-border);
            border-radius: 20px;
            padding: 1.05rem;
            box-shadow: 0 10px 24px rgba(19,41,75,0.045);
            transition: all .18s ease;
        }}

        .score-card:hover {{
            transform: translateY(-2px);
            box-shadow: 0 18px 32px rgba(19,41,75,0.075);
            border-color: rgba(11,93,134,0.25);
        }}

        .score-title {{
            color: var(--text-muted);
            font-size: 0.80rem;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            font-weight: 800;
        }}

        .score-number {{
            color: var(--ugfs-navy);
            font-size: 2.1rem;
            font-weight: 800;
            margin-top: 0.35rem;
        }}

        .score-pill {{
            display: inline-block;
            margin-top: 0.55rem;
            padding: 0.38rem 0.68rem;
            border-radius: 999px;
            background: #EAF3F8;
            color: var(--ugfs-blue);
            font-size: 0.82rem;
            font-weight: 800;
        }}

        .score-sub {{
            color: var(--text-muted);
            margin-top: 0.38rem;
            font-size: 0.9rem;
        }}

        .stButton > button,
        .stDownloadButton > button {{
            border-radius: 16px !important;
            min-height: 3.2rem;
            font-size: 0.96rem;
            font-weight: 800;
            border: 1px solid var(--ugfs-border);
            background: white;
            color: var(--ugfs-navy);
            box-shadow: 0 10px 24px rgba(19,41,75,0.055);
            transition: all .18s ease;
        }}

        .stButton > button:hover,
        .stDownloadButton > button:hover {{
            transform: translateY(-2px);
            border-color: rgba(11,93,134,0.35);
            color: var(--ugfs-blue);
            box-shadow: 0 18px 30px rgba(19,41,75,0.09);
        }}

        .stButton > button[kind="primary"] {{
            background: linear-gradient(135deg, var(--ugfs-blue) 0%, var(--ugfs-navy) 100%) !important;
            color: white !important;
            border: none !important;
            box-shadow: 0 16px 30px rgba(11,93,134,0.25) !important;
        }}

        .stButton > button[kind="primary"]:hover {{
            box-shadow: 0 20px 36px rgba(11,93,134,0.32) !important;
        }}

        [data-testid="stDataFrame"] {{
            border: 1px solid var(--ugfs-border);
            border-radius: 18px;
            overflow: hidden;
            box-shadow: 0 8px 24px rgba(19,41,75,0.05);
        }}

        div[data-baseweb="notification"] {{
            border-radius: 16px;
            border: 1px solid var(--ugfs-border);
        }}

        .stProgress > div > div > div > div {{
            background: linear-gradient(90deg, var(--ugfs-blue), var(--ugfs-accent));
        }}

        .status-banner {{
            background: {WARNING_BG};
            border: 1px solid #EEE2B5;
            border-radius: 16px;
            padding: 0.85rem 1rem;
            color: #8E6B00;
            font-weight: 700;
            margin: 0.6rem 0;
        }}

        .success-banner {{
            background: {SUCCESS_BG};
            border: 1px solid #CFE8D8;
            border-radius: 16px;
            padding: 0.85rem 1rem;
            color: #1D6B43;
            font-weight: 700;
            margin: 0.6rem 0;
        }}

        .error-banner {{
            background: {ERROR_BG};
            border: 1px solid #FFD1CD;
            border-radius: 16px;
            padding: 0.85rem 1rem;
            color: #A33126;
            font-weight: 700;
            margin: 0.6rem 0;
        }}

        .mini-note {{
            font-size: 0.86rem;
            color: var(--text-muted);
            line-height: 1.45;
        }}

        @media (max-width: 1100px) {{
            .metric-grid {{
                grid-template-columns: 1fr 1fr;
            }}
            .score-grid {{
                grid-template-columns: 1fr;
            }}
            .topbar {{
                flex-direction: column;
                align-items: flex-start;
            }}
            .doc-list {{
                grid-template-columns: 1fr;
            }}
        }}

        @media (max-width: 640px) {{
            .metric-grid {{
                grid-template-columns: 1fr;
            }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# Sidebar
# ============================================================

def sidebar_block():
    with st.sidebar:
        st.markdown("<div class='sidebar-brand'>", unsafe_allow_html=True)

        if LOGO and LOGO.exists():
            logo_base64 = image_to_base64(LOGO)
            st.markdown(
                f"""
                <img class="sidebar-logo" src="data:image/png;base64,{logo_base64}" />
                """,
                unsafe_allow_html=True,
            )
        else:
            st.markdown("<div class='brand-fallback'>UGFS</div>", unsafe_allow_html=True)

        st.markdown(
            """
            <div class="sidebar-app-title">LegalTech AI Assistant</div>
            <div class="sidebar-subtitle">UGFS North Africa</div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("<div class='side-divider'></div>", unsafe_allow_html=True)

        st.markdown("<div class='sidebar-section-label'>Menu</div>", unsafe_allow_html=True)
        st.markdown(
            """
            <div class="side-nav">
                <a href="#dashboard">Dashboard</a>
                <a href="#documents">Documents</a>
                <a href="#actions">Actions</a>
                <a href="#scores">Scores</a>
                <a href="#results">Results</a>
                <a href="#exports">Exports</a>
                <a href="#feedback">Feedback</a>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("<div class='sidebar-section-label'>PDF Upload</div>", unsafe_allow_html=True)

        uploaded = st.file_uploader(
            "Upload LegalTech PDF",
            type=["pdf"],
            accept_multiple_files=True,
            label_visibility="collapsed",
        )

        save_clicked = st.button("Save PDFs", use_container_width=True)

        if uploaded and save_clicked:
            saved_count = 0
            for f in uploaded:
                path = save_uploaded_pdf(f)
                saved_count += 1
                st.success(f"Saved: {path.name}")

            if saved_count:
                st.session_state.last_message = f"{saved_count} PDF file(s) saved successfully."

        st.markdown(
            f"""
            <div class="sidebar-mini-status">
                <strong>Runtime</strong><br>
                Local model: {OLLAMA_MODEL}<br>
                Mode: Manual PDF MVP
            </div>
            """,
            unsafe_allow_html=True,
        )


# ============================================================
# Header / navigation
# ============================================================

def topbar():
    st.markdown("<div id='dashboard'></div>", unsafe_allow_html=True)

    st.markdown(
        f"""
        <div class="topbar">
            <div class="topbar-left">
                <h1>UGFS-NA LegalTech AI Assistant</h1>
                <p>Manual PDF analysis dashboard · OCR · Local LLM · Excel feedback loop</p>
            </div>
            <div class="topbar-status">Local model · {OLLAMA_MODEL}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def section_nav():
    st.markdown(
        """
        <div class="section-nav">
            <a href="#dashboard">Overview</a>
            <a href="#documents">Documents</a>
            <a href="#actions">Actions</a>
            <a href="#scores">Scores</a>
            <a href="#results">Results</a>
            <a href="#exports">Exports</a>
            <a href="#feedback">Feedback</a>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# Data helpers
# ============================================================

def count_feedback_rules():
    memory = load_feedback_memory()

    if isinstance(memory, dict):
        if "rules" in memory and isinstance(memory["rules"], list):
            return len(memory["rules"])
        return len(memory)

    if isinstance(memory, list):
        return len(memory)

    return 0


def count_fallback_rows(rows: list[dict]) -> int:
    total = 0

    for row in rows:
        summary = str(row.get("Résumé_IA", "")).lower()
        method = str(row.get("Scoring_Method", "")).lower()
        action = str(row.get("Action_Recommandée_IA", "")).lower()

        if (
            "indisponible" in summary
            or "json invalide" in summary
            or "httperror" in action
            or "baseline_rules" in method
        ):
            total += 1

    return total


def build_pdf_table(pdfs: list[Path]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "PDF": pdf.name,
                "Size_KB": round(pdf.stat().st_size / 1024, 2),
                "Status": "Ready for OCR",
            }
            for pdf in pdfs
        ]
    )


def get_selected_result():
    if not st.session_state.results:
        return None

    options = {
        row.get("Nom_PDF", f"Document {i + 1}"): row
        for i, row in enumerate(st.session_state.results)
    }

    selected_name = st.selectbox(
        "Select analyzed document",
        list(options.keys()),
        key="selected_result_pdf",
    )

    return options[selected_name]


# ============================================================
# UI sections
# ============================================================

def metrics_overview(pdf_count: int, results_count: int, feedback_count: int):
    fallback_count = count_fallback_rows(st.session_state.results)

    st.markdown(
        f"""
        <div class="metric-grid">
            <div class="metric-card">
                <div class="metric-label">PDFs disponibles</div>
                <div class="metric-value">{pdf_count}</div>
                <div class="metric-sub">Documents prêts pour analyse</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Analyses en session</div>
                <div class="metric-value">{results_count}</div>
                <div class="metric-sub">Résultats actuellement chargés</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Règles feedback</div>
                <div class="metric-value">{feedback_count}</div>
                <div class="metric-sub">Mémoire construite depuis les corrections</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Mode</div>
                <div class="metric-value" style="font-size:1.08rem; margin-top:0.75rem;">
                    MVP · PDF manuel
                </div>
                <div class="metric-sub">{fallback_count} fallback / OCR → Ollama → Excel</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def documents_section(pdfs_available: list[Path]):
    st.markdown("<div id='documents'></div>", unsafe_allow_html=True)
    st.markdown("<div class='section-title'>Uploaded PDFs</div>", unsafe_allow_html=True)

    if pdfs_available:
        st.dataframe(
            build_pdf_table(pdfs_available),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.markdown(
            """
            <div class="panel">
                No uploaded PDFs yet. Upload one or more LegalTech PDFs from the sidebar, then click
                <strong>Save PDFs</strong>.
            </div>
            """,
            unsafe_allow_html=True,
        )


def actions_section():
    st.markdown("<div id='actions'></div>", unsafe_allow_html=True)
    st.markdown("<div class='section-title'>Action Center</div>", unsafe_allow_html=True)

    st.markdown(
        """
        <div class="workflow-panel">
            <div class="workflow-title">Main workflow</div>
            <div class="workflow-sub">
                Use these actions in order: analyze the saved PDFs, export results to Excel,
                then import the corrected Excel in the Feedback panel.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns([1, 1, 1], gap="medium")

    with c1:
        analyze_clicked = st.button(
            "Analyser les PDFs",
            use_container_width=True,
            type="primary",
        )

    with c2:
        export_clicked = st.button(
            "Exporter vers Excel",
            use_container_width=True,
        )

    with c3:
        clear_clicked = st.button(
            "Clear session results",
            use_container_width=True,
        )

    return analyze_clicked, export_clicked, clear_clicked


def score_cards(row):
    risk_score = row.get("Score_Risque_IA", 0)
    risk_level = row.get("Niveau_Risque_IA", "-")
    opp_score = row.get("Score_Opportunité_IA", 0)
    opp_level = row.get("Niveau_Opportunité_IA", "-")
    confidence = row.get("Confiance_IA", 0)

    st.markdown("<div id='scores'></div>", unsafe_allow_html=True)
    st.markdown("<div class='section-title'>Scores</div>", unsafe_allow_html=True)

    st.markdown(
        f"""
        <div class="score-grid">
            <div class="score-card">
                <div class="score-title">Risk score</div>
                <div class="score-number">{risk_score}</div>
                <div class="score-pill">{risk_level}</div>
                <div class="score-sub">Risk detected from AI/rules</div>
            </div>
            <div class="score-card">
                <div class="score-title">Opportunity score</div>
                <div class="score-number">{opp_score}</div>
                <div class="score-pill">{opp_level}</div>
                <div class="score-sub">Opportunity detected from AI/rules</div>
            </div>
            <div class="score-card">
                <div class="score-title">Confidence</div>
                <div class="score-number">{confidence}</div>
                <div class="score-pill">AI confidence</div>
                <div class="score-sub">Depends on OCR and LLM output quality</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.expander("View score details", expanded=True):
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**Document**")
            st.write(row.get("Nom_PDF", "-"))

            st.markdown("**Société**")
            st.write(row.get("Société", "-"))

            st.markdown("**Catégorie**")
            st.write(row.get("Catégorie", "-"))

            st.markdown("**Type d'événement**")
            st.write(row.get("Type_Événement_IA", "-"))

        with col2:
            st.markdown("**Action recommandée**")
            st.write(row.get("Action_Recommandée_IA", "-"))

            st.markdown("**Scoring method**")
            st.write(row.get("Scoring_Method", "-"))

            st.markdown("**Résumé**")
            st.write(row.get("Résumé_IA", "-"))

    with st.expander("View detected risks / opportunities"):
        st.markdown("**Risques détectés**")
        st.write(row.get("Risques_Détectés_IA", "-"))

        st.markdown("**Opportunités détectées**")
        st.write(row.get("Opportunités_Détectées_IA", "-"))


def empty_score_cards():
    st.markdown("<div id='scores'></div>", unsafe_allow_html=True)
    st.markdown("<div class='section-title'>Scores</div>", unsafe_allow_html=True)

    st.markdown(
        """
        <div class="score-grid">
            <div class="score-card">
                <div class="score-title">Risk score</div>
                <div class="score-number">--</div>
                <div class="score-pill">No data</div>
                <div class="score-sub">Run an analysis to populate this section</div>
            </div>
            <div class="score-card">
                <div class="score-title">Opportunity score</div>
                <div class="score-number">--</div>
                <div class="score-pill">No data</div>
                <div class="score-sub">Run an analysis to populate this section</div>
            </div>
            <div class="score-card">
                <div class="score-title">Confidence</div>
                <div class="score-number">--</div>
                <div class="score-pill">No data</div>
                <div class="score-sub">Run an analysis to populate this section</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def results_section():
    st.markdown("<div id='results'></div>", unsafe_allow_html=True)
    st.markdown("<div class='section-title'>Results</div>", unsafe_allow_html=True)

    if st.session_state.results:
        df = pd.DataFrame(st.session_state.results)
        st.dataframe(df, use_container_width=True, hide_index=True)

        fallback_count = count_fallback_rows(st.session_state.results)
        if fallback_count:
            st.markdown(
                f"""
                <div class="status-banner">
                    {fallback_count} result(s) used fallback logic. This usually means Ollama is not ready,
                    the model name is wrong, or the LLM returned invalid JSON.
                </div>
                """,
                unsafe_allow_html=True,
            )
    else:
        st.markdown(
            "<div class='panel'>No analysis results yet.</div>",
            unsafe_allow_html=True,
        )


def exports_panel():
    st.markdown("<div id='exports'></div>", unsafe_allow_html=True)
    st.markdown("<div class='section-title'>Exports</div>", unsafe_allow_html=True)

    if st.session_state.last_excel_path and Path(st.session_state.last_excel_path).exists():
        excel_path = Path(st.session_state.last_excel_path)

        st.download_button(
            "Download Excel file",
            data=excel_path.read_bytes(),
            file_name=excel_path.name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

        st.markdown(
            f"""
            <div class="mini-note">
                Last export: <strong>{excel_path.name}</strong>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.button("Download Excel file", disabled=True, use_container_width=True)
        st.markdown(
            """
            <div class="mini-note">
                Run an analysis and click <strong>Exporter vers Excel</strong> first.
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.download_button(
        "Download PDF report",
        data=b"",
        file_name="ugfs_legaltech_report.pdf",
        mime="application/pdf",
        disabled=True,
        use_container_width=True,
    )


def feedback_panel():
    st.markdown("<div id='feedback'></div>", unsafe_allow_html=True)
    st.markdown("<div class='section-title'>Feedback</div>", unsafe_allow_html=True)

    st.markdown(
        """
        <div class="panel">
            Upload the corrected Excel file here after human review. The app will update
            feedback memory and the training dataset.
        </div>
        """,
        unsafe_allow_html=True,
    )

    corrected_file = st.file_uploader(
        "Importer Excel corrigé",
        type=["xlsx"],
        key="main_corrected_file",
    )

    if corrected_file is not None:
        try:
            df_corr = read_corrected_excel(corrected_file)
            n_rules = update_memory_from_excel(df_corr)
            n_training = append_training_dataset(df_corr)

            st.markdown(
                f"""
                <div class="success-banner">
                    Feedback memory updated with {n_rules} corrected row(s).
                    Training dataset updated with {n_training} usable row(s).
                </div>
                """,
                unsafe_allow_html=True,
            )
        except Exception as e:
            st.markdown(
                f"""
                <div class="error-banner">
                    Could not import corrected Excel. Details: {e}
                </div>
                """,
                unsafe_allow_html=True,
            )

    view_memory = st.button("Voir mémoire feedback", use_container_width=True)

    if view_memory:
        memory = load_feedback_memory()

        if memory:
            st.json(memory)
        else:
            st.markdown(
                "<div class='panel'>No feedback rules yet.</div>",
                unsafe_allow_html=True,
            )


# ============================================================
# Analysis / export handlers
# ============================================================

def run_pdf_analysis():
    pdfs = list_pdf_files()

    if not pdfs:
        st.markdown(
            "<div class='status-banner'>No PDF found in data/pdf_raw. Upload a PDF first.</div>",
            unsafe_allow_html=True,
        )
        return

    rows = []
    progress = st.progress(0)

    for idx, pdf_path in enumerate(pdfs, start=1):
        with st.status(f"Analyzing {pdf_path.name}", expanded=False):
            try:
                ocr = extract_pdf_text(pdf_path)
                extracted_text = ocr.get("text", "")

                if len(extracted_text.strip()) < 50:
                    st.warning(
                        f"{pdf_path.name}: extracted text is too short. "
                        "Check Tesseract/Poppler if this PDF is scanned."
                    )
                    progress.progress(idx / len(pdfs))
                    continue

                analysis = analyze_legal_text(
                    extracted_text,
                    ocr_quality=ocr.get("ocr_quality", 0),
                )

                analysis = score_analysis(analysis, extracted_text)
                rows.append(analysis_to_row(analysis, pdf_path.name, idx))

            except Exception as e:
                st.error(f"{pdf_path.name}: analysis failed. Details: {e}")

            progress.progress(idx / len(pdfs))

    st.session_state.results = rows

    if rows:
        st.markdown(
            f"<div class='success-banner'>Analysis complete: {len(rows)} PDF(s).</div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            "<div class='status-banner'>No PDF could be analyzed. Check OCR/text extraction.</div>",
            unsafe_allow_html=True,
        )


def run_excel_export():
    if not st.session_state.results:
        st.markdown(
            "<div class='status-banner'>No results to export. Run analysis first.</div>",
            unsafe_allow_html=True,
        )
        return

    try:
        path = export_results(st.session_state.results)
        st.session_state.last_excel_path = path

        st.markdown(
            f"<div class='success-banner'>Excel exported successfully: {path.name}</div>",
            unsafe_allow_html=True,
        )
    except Exception as e:
        st.markdown(
            f"<div class='error-banner'>Excel export failed. Details: {e}</div>",
            unsafe_allow_html=True,
        )


# ============================================================
# Main app
# ============================================================

inject_css()
sidebar_block()

if "results" not in st.session_state:
    st.session_state.results = []

if "last_excel_path" not in st.session_state:
    st.session_state.last_excel_path = None

if "last_message" not in st.session_state:
    st.session_state.last_message = None

topbar()
section_nav()

pdfs_available = list_pdf_files()
feedback_count = count_feedback_rules()

metrics_overview(
    pdf_count=len(pdfs_available),
    results_count=len(st.session_state.results),
    feedback_count=feedback_count,
)

documents_section(pdfs_available)

analyze_clicked, export_clicked, clear_clicked = actions_section()

if clear_clicked:
    st.session_state.results = []
    st.session_state.last_excel_path = None
    st.markdown(
        "<div class='success-banner'>Session results cleared. PDFs remain saved in data/pdf_raw.</div>",
        unsafe_allow_html=True,
    )

if analyze_clicked:
    run_pdf_analysis()

if export_clicked:
    run_excel_export()

main_left, main_right = st.columns([1.55, 1.05], gap="large")

with main_left:
    selected_row = get_selected_result()

    if selected_row:
        score_cards(selected_row)
    else:
        empty_score_cards()

    results_section()

with main_right:
    exports_panel()
    feedback_panel()