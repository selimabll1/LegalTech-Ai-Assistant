from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from config import OUTPUT_EXCEL_DIR


BASE_COLUMNS = [
    "ID_Annonce",
    "Date_Email",
    "Nom_PDF",
    "Société",
    "Catégorie",
    "Type_Événement_IA",
    "Résumé_IA",
    "Risques_Détectés_IA",
    "Opportunités_Détectées_IA",
    "Score_Risque_IA",
    "Niveau_Risque_IA",
    "Score_Opportunité_IA",
    "Niveau_Opportunité_IA",
    "Action_Recommandée_IA",
    "Confiance_IA",
    "Scoring_Method",
]

CORRECTION_COLUMNS = [
    "Statut_Revue",
    "Type_Événement_Corrigé",
    "Résumé_Corrigé",
    "Risques_Corrigés",
    "Opportunités_Corrigées",
    "Score_Risque_Corrigé",
    "Score_Opportunité_Corrigé",
    "Action_Corrigée",
    "Commentaire_Humain",
    "Validateur",
    "Date_Validation",
]


def safe_text(value: Any, default: str = "") -> str:
    """
    Converts any value to clean text.
    Important: if value is already a string, do NOT join it letter by letter.
    """
    if value is None:
        return default

    if isinstance(value, str):
        return value.strip()

    if isinstance(value, list):
        return "; ".join(str(item).strip() for item in value if str(item).strip())

    if isinstance(value, tuple):
        return "; ".join(str(item).strip() for item in value if str(item).strip())

    if isinstance(value, dict):
        return str(value)

    return str(value).strip()


def safe_number(value: Any, default: float = 0) -> float:
    try:
        return round(float(value), 2)
    except Exception:
        return default


def get_first(analysis: dict, *keys, default: Any = "") -> Any:
    for key in keys:
        if key in analysis and analysis.get(key) not in [None, ""]:
            return analysis.get(key)
    return default


def analysis_to_row(analysis: dict, pdf_name: str, index: int) -> dict:
    """
    Converts one AI analysis dictionary into one Excel-ready row.
    """

    risk_score = get_first(
        analysis,
        "Score_Risque_IA",
        "score_risque",
        "risk_score",
        default=0,
    )

    opportunity_score = get_first(
        analysis,
        "Score_Opportunité_IA",
        "score_opportunite",
        "opportunity_score",
        default=0,
    )

    risk_level = get_first(
        analysis,
        "Niveau_Risque_IA",
        "niveau_risque",
        "risk_level",
        default="-",
    )

    opportunity_level = get_first(
        analysis,
        "Niveau_Opportunité_IA",
        "niveau_opportunite",
        "opportunity_level",
        default="-",
    )

    confidence = get_first(
        analysis,
        "Confiance_IA",
        "niveau_confiance",
        "confiance",
        "confidence",
        default=0,
    )

    scoring_method = get_first(
        analysis,
        "Scoring_Method",
        "scoring_method",
        default="-",
    )

    row = {
        "ID_Annonce": f"ANN-{index:04d}",
        "Date_Email": "MVP manuel",
        "Nom_PDF": pdf_name,

        "Société": safe_text(
            get_first(analysis, "Société", "societe", "société", default="À vérifier")
        ),

        "Catégorie": safe_text(
            get_first(analysis, "Catégorie", "categorie", "catégorie", default="À vérifier")
        ),

        "Type_Événement_IA": safe_text(
            get_first(
                analysis,
                "Type_Événement_IA",
                "type_evenement",
                "type_événement",
                default="À classifier manuellement",
            )
        ),

        "Résumé_IA": safe_text(
            get_first(analysis, "Résumé_IA", "resume", "résumé", default="")
        ),

        "Risques_Détectés_IA": safe_text(
            get_first(
                analysis,
                "Risques_Détectés_IA",
                "risques_detectes",
                "risques",
                default="",
            )
        ),

        "Opportunités_Détectées_IA": safe_text(
            get_first(
                analysis,
                "Opportunités_Détectées_IA",
                "opportunites_detectees",
                "opportunites",
                "opportunities",
                default="",
            )
        ),

        "Score_Risque_IA": safe_number(risk_score, 0),
        "Niveau_Risque_IA": safe_text(risk_level, "-"),

        "Score_Opportunité_IA": safe_number(opportunity_score, 0),
        "Niveau_Opportunité_IA": safe_text(opportunity_level, "-"),

        "Action_Recommandée_IA": safe_text(
            get_first(
                analysis,
                "Action_Recommandée_IA",
                "action_recommandee",
                "action_recommandée",
                default="Revue humaine recommandée",
            )
        ),

        "Confiance_IA": safe_number(confidence, 0),
        "Scoring_Method": safe_text(scoring_method, "-"),
    }

    for col in CORRECTION_COLUMNS:
        row[col] = ""

    return row


def export_results(results: list[dict]) -> Path:
    """
    Exports analysis results to Excel.
    """
    OUTPUT_EXCEL_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = OUTPUT_EXCEL_DIR / f"legaltech_analysis_{timestamp}.xlsx"

    df = pd.DataFrame(results)

    for col in BASE_COLUMNS + CORRECTION_COLUMNS:
        if col not in df.columns:
            df[col] = ""

    df = df[BASE_COLUMNS + CORRECTION_COLUMNS]

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Analyse_LegalTech")

        worksheet = writer.sheets["Analyse_LegalTech"]

        for column_cells in worksheet.columns:
            column_letter = column_cells[0].column_letter
            max_length = 0

            for cell in column_cells:
                value = str(cell.value) if cell.value is not None else ""
                max_length = max(max_length, len(value))

            worksheet.column_dimensions[column_letter].width = min(max_length + 2, 45)

    return output_path


def read_corrected_excel(uploaded_file) -> pd.DataFrame:
    """
    Reads corrected Excel uploaded by the user.
    """
    return pd.read_excel(uploaded_file)