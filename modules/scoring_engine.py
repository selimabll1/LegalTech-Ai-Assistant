import joblib
from config import MODELS_DIR
from modules.feature_extractor import extract_features


def level_from_score(score: int, critical_label: str = "Critique") -> str:
    if score <= 30:
        return "Faible"
    if score <= 60:
        return "Moyen"
    if score <= 80:
        return "Élevé"
    return critical_label


def baseline_scores(features: dict) -> tuple[int, int]:
    """Explainable MVP baseline.

    Important: this is not the final enterprise scoring model. It is the initial
    baseline used before UGFS has enough human-corrected examples for ML.
    """
    risk = 0
    opportunity = 0

    if features["has_liquidation"]:
        risk += 45
    if features["has_collective_procedure"]:
        risk += 35
    if features["has_capital_event"]:
        risk += 22
        opportunity += 25
    if features["has_ma_asset_sale"]:
        risk += 15
        opportunity += 30
    if features["has_governance"]:
        risk += 12
        opportunity += 8
    if features["has_shareholder_change"]:
        risk += 12
        opportunity += 12
    if features["mentions_amount"]:
        risk += 10
        opportunity += 8
    if features["has_deadline"]:
        risk += 8
        opportunity += 10

    info_quality = int(round(features["ocr_quality"] * 10))
    risk += info_quality
    opportunity += info_quality

    return min(100, risk), min(100, opportunity)


def ml_predict_if_available(features: dict, fallback_risk: int, fallback_opp: int) -> tuple[int, int, str]:
    """Use trained regressors if available; otherwise keep baseline scores."""
    risk_model_path = MODELS_DIR / "risk_regressor.joblib"
    opp_model_path = MODELS_DIR / "opportunity_regressor.joblib"
    feature_order_path = MODELS_DIR / "feature_order.joblib"

    if not (risk_model_path.exists() and opp_model_path.exists() and feature_order_path.exists()):
        return fallback_risk, fallback_opp, "baseline_rules"

    feature_order = joblib.load(feature_order_path)
    X = [[features.get(k, 0) for k in feature_order]]
    risk_model = joblib.load(risk_model_path)
    opp_model = joblib.load(opp_model_path)
    risk = int(max(0, min(100, risk_model.predict(X)[0])))
    opp = int(max(0, min(100, opp_model.predict(X)[0])))
    return risk, opp, "ml_regression"


def compute_confidence(analysis: dict) -> float:
    """Confidence is a system-quality indicator, not a legal certainty."""
    required = ["societe", "type_evenement", "categorie", "resume", "action_recommandee"]
    completeness = sum(bool(analysis.get(k)) for k in required) / len(required)
    ocr_quality = float(analysis.get("ocr_quality", 0.6))
    llm_conf = float(analysis.get("niveau_confiance_llm", 0.5))
    json_score = 1.0 if analysis.get("json_valid", True) else 0.3
    confidence = 0.35 * ocr_quality + 0.25 * completeness + 0.20 * json_score + 0.20 * llm_conf
    return round(max(0, min(1, confidence)), 3)


def score_analysis(analysis: dict, text: str) -> dict:
    features = extract_features(analysis, text)
    base_risk, base_opp = baseline_scores(features)
    risk, opp, method = ml_predict_if_available(features, base_risk, base_opp)
    analysis.update({
        "score_risque": risk,
        "niveau_risque": level_from_score(risk),
        "score_opportunite": opp,
        "niveau_opportunite": level_from_score(opp, critical_label="Très élevé"),
        "niveau_confiance": compute_confidence(analysis),
        "scoring_method": method,
        "features": features,
    })
    return analysis
