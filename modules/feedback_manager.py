import json
from datetime import datetime
import pandas as pd
from config import FEEDBACK_MEMORY_PATH, TRAINING_DATASET_PATH


def load_feedback_memory() -> list[dict]:
    if not FEEDBACK_MEMORY_PATH.exists():
        return []
    try:
        return json.loads(FEEDBACK_MEMORY_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def save_feedback_memory(items: list[dict]) -> None:
    FEEDBACK_MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    FEEDBACK_MEMORY_PATH.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def classify_error(row: pd.Series) -> str:
    if str(row.get("Type_Événement_Corrigé", "")).strip() and str(row.get("Type_Événement_Corrigé", "")).lower() != "nan":
        return "Erreur de classification"
    if str(row.get("Score_Risque_Corrigé", "")).strip() and str(row.get("Score_Risque_Corrigé", "")).lower() != "nan":
        return "Erreur de scoring"
    if str(row.get("Résumé_Corrigé", "")).strip() and str(row.get("Résumé_Corrigé", "")).lower() != "nan":
        return "Erreur de résumé"
    if str(row.get("Action_Corrigée", "")).strip() and str(row.get("Action_Corrigée", "")).lower() != "nan":
        return "Erreur de recommandation"
    return "Correction générale"


def _clean(value) -> str:
    value = "" if pd.isna(value) else str(value).strip()
    return "" if value.lower() == "nan" else value


def row_to_feedback_rule(row: pd.Series) -> dict:
    pred = _clean(row.get("Type_Événement_IA", ""))
    corr = _clean(row.get("Type_Événement_Corrigé", "")) or pred
    company = _clean(row.get("Société", ""))
    comment = _clean(row.get("Commentaire_Humain", ""))
    score_risk = _clean(row.get("Score_Risque_Corrigé", ""))
    score_opp = _clean(row.get("Score_Opportunité_Corrigé", ""))
    action = _clean(row.get("Action_Corrigée", ""))

    rule = f"Pour une annonce similaire à '{pred}', vérifier si elle doit être classée comme '{corr}'."
    if score_risk:
        rule += f" Score risque validé/corrigé indicatif: {score_risk}."
    if score_opp:
        rule += f" Score opportunité validé/corrigé indicatif: {score_opp}."
    if action:
        rule += f" Action recommandée validée: {action}."
    if comment:
        rule += f" Indice humain: {comment}"

    return {
        "date_validation": datetime.now().strftime("%Y-%m-%d"),
        "validateur": _clean(row.get("Validateur", "")),
        "societe": company,
        "type_erreur": classify_error(row),
        "prediction_ia": pred,
        "correction_humaine": corr,
        "regle_apprise": rule,
        "score_risque_corrige": score_risk,
        "score_opportunite_corrige": score_opp,
        "action_corrigee": action,
        "source_id_annonce": _clean(row.get("ID_Annonce", "")),
    }


def update_memory_from_excel(df: pd.DataFrame) -> int:
    memory = load_feedback_memory()
    if "Statut_Revue" not in df.columns:
        return 0
    corrected = df[df["Statut_Revue"].astype(str).str.lower().str.strip().eq("corrigé")]
    new_items = [row_to_feedback_rule(row) for _, row in corrected.iterrows()]
    memory.extend(new_items)
    save_feedback_memory(memory)
    return len(new_items)


def append_training_dataset(df: pd.DataFrame) -> int:
    """Store Validé + Corrigé rows for future supervised ML training."""
    if "Statut_Revue" not in df.columns:
        return 0
    usable = df[df["Statut_Revue"].astype(str).str.lower().str.strip().isin(["validé", "corrigé"])]
    if usable.empty:
        return 0
    if TRAINING_DATASET_PATH.exists():
        old = pd.read_excel(TRAINING_DATASET_PATH)
        usable = pd.concat([old, usable], ignore_index=True)
    TRAINING_DATASET_PATH.parent.mkdir(parents=True, exist_ok=True)
    usable.to_excel(TRAINING_DATASET_PATH, index=False)
    return len(usable)
