"""Explainable LegalTech scoring with factual validation.

Business scores are deterministic and event-based. OCR quality affects only
confidence and never increases risk or opportunity.
"""

from __future__ import annotations

import re
from typing import Any

import joblib

from config import MODELS_DIR
from modules.fact_validator import validate_and_correct_analysis
from modules.feature_extractor import extract_features


SCORING_VERSION = "legaltech_scoring_v6"

# Generic LegalTech prioritisation. Opportunity is not an UGFS investment
# recommendation until UGFS-specific strategic criteria are configured.
EVENT_BASE_SCORES: dict[str, tuple[int, int, str]] = {
    "CONSTITUTION_SOCIETE": (20, 35, "Création d'une nouvelle structure sans signal négatif explicite."),
    "SOUSCRIPTION_CAPITAL": (25, 55, "Fenêtre de souscription explicite, à confirmer selon la stratégie UGFS."),
    "AUGMENTATION_CAPITAL": (30, 65, "Événement de financement pouvant créer une opportunité à analyser."),
    "DISSOLUTION": (75, 20, "Fin anticipée de la société ou décision de dissolution."),
    "LIQUIDATION": (85, 25, "Liquidation en cours avec impact élevé sur la continuité."),
    "CLOTURE_LIQUIDATION": (55, 10, "Clôture d'une liquidation, événement important mais achevé."),
    "REDRESSEMENT_JUDICIAIRE": (90, 20, "Procédure judiciaire affectant fortement la continuité et les créanciers."),
    "FAILLITE": (95, 20, "Faillite ou procédure collective critique."),
    "CLOTURE_FAILLITE": (60, 10, "Clôture d'une faillite, avec risque historique élevé mais procédure terminée."),
    "VENTE_FONDS_COMMERCE": (35, 65, "Cession d'un actif commercial pouvant constituer une opportunité transactionnelle."),
    "LOCATION_GERANCE": (25, 45, "Mise en location-gérance d'un fonds de commerce."),
    "VENTE_ENCHERES_SAISIE": (80, 70, "Saisie ou adjudication : risque élevé et potentiel d'acquisition."),
    "AVIS_CREANCIERS": (70, 15, "Appel ou délai de déclaration des créances."),
    "NOMINATION_DIRIGEANT": (25, 15, "Changement de direction à surveiller."),
    "NOMINATION_COMMISSAIRE": (15, 10, "Nomination de contrôle/audit, généralement peu risquée seule."),
    "CHANGEMENT_GOUVERNANCE": (30, 15, "Modification de gouvernance nécessitant une revue."),
    "CONVOCATION_AGO": (10, 15, "Convocation ordinaire sans signal négatif explicite."),
    "CONVOCATION_AGE": (15, 25, "Assemblée extraordinaire pouvant porter sur une opération structurante."),
    "CONSTITUTION_ASSOCIATION": (10, 15, "Création associative, généralement faible en risque financier."),
    "RECTIFICATIF": (10, 5, "Rectification administrative ou éditoriale."),
    "AUTRE": (20, 15, "Événement non classé, à revoir manuellement."),
}


def level_from_score(score: int, critical_label: str = "Critique") -> str:
    if score < 30:
        return "Faible"
    if score < 60:
        return "Moyen"
    if score < 80:
        return "Élevé"
    return critical_label


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").casefold()).strip()


def _has_any(text: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def baseline_scores(
    analysis: dict[str, Any],
    text: str,
) -> tuple[int, int, dict[str, Any]]:
    """Return transparent scores and a complete point-by-point explanation."""
    event_code = str(analysis.get("type_evenement_code", "AUTRE"))
    if event_code not in EVENT_BASE_SCORES:
        event_code = "AUTRE"

    base_risk, base_opportunity, base_reason = EVENT_BASE_SCORES[event_code]
    risk = base_risk
    opportunity = base_opportunity

    risk_breakdown: list[dict[str, Any]] = [
        {
            "facteur": f"Événement principal : {event_code}",
            "points": base_risk,
            "justification": base_reason,
        }
    ]
    opportunity_breakdown: list[dict[str, Any]] = [
        {
            "facteur": f"Événement principal : {event_code}",
            "points": base_opportunity,
            "justification": base_reason,
        }
    ]

    secondary = analysis.get("evenements_secondaires", [])
    if not isinstance(secondary, list):
        secondary = []

    if "SOUSCRIPTION_CAPITAL" in secondary and event_code == "CONSTITUTION_SOCIETE":
        opportunity += 10
        opportunity_breakdown.append(
            {
                "facteur": "Souscription au capital détectée",
                "points": 10,
                "justification": "Une fenêtre de souscription existe, sous réserve d'éligibilité et d'intérêt stratégique UGFS.",
            }
        )

    haystack = _normalize_text(text)

    if _has_any(
        haystack,
        [r"d[ée]lai de \d+ jours", r"dans un d[ée]lai", r"au plus tard", r"date limite"],
    ):
        risk += 5
        risk_breakdown.append(
            {
                "facteur": "Délai légal ou opérationnel explicite",
                "points": 5,
                "justification": "Une action peut être requise dans une fenêtre limitée.",
            }
        )

    if _has_any(
        haystack,
        [r"tribunal", r"jugement", r"ordonnance", r"juge[- ]commissaire", r"administrateur judiciaire"],
    ) and event_code not in {
        "REDRESSEMENT_JUDICIAIRE",
        "FAILLITE",
        "CLOTURE_FAILLITE",
        "VENTE_ENCHERES_SAISIE",
    }:
        risk += 5
        risk_breakdown.append(
            {
                "facteur": "Intervention judiciaire explicite",
                "points": 5,
                "justification": "Le texte mentionne une décision ou une autorité judiciaire.",
            }
        )

    if _has_any(
        haystack,
        [r"cr[ée]anciers", r"d[ée]claration des cr[ée]ances", r"produire leurs titres de cr[ée]ances"],
    ) and event_code not in {"AVIS_CREANCIERS", "REDRESSEMENT_JUDICIAIRE"}:
        risk += 8
        risk_breakdown.append(
            {
                "facteur": "Créanciers explicitement concernés",
                "points": 8,
                "justification": "Le texte prévoit une démarche ou un délai pour les créanciers.",
            }
        )

    supported_risks = analysis.get("risques_avec_preuves", [])
    if isinstance(supported_risks, list) and supported_risks:
        points = min(6, len(supported_risks) * 2)
        risk += points
        risk_breakdown.append(
            {
                "facteur": "Risques appuyés par une citation source",
                "points": points,
                "justification": f"{len(supported_risks)} risque(s) possède(nt) une preuve textuelle validée.",
            }
        )

    supported_opportunities = analysis.get("opportunites_avec_preuves", [])
    if isinstance(supported_opportunities, list) and supported_opportunities:
        points = min(6, len(supported_opportunities) * 2)
        opportunity += points
        opportunity_breakdown.append(
            {
                "facteur": "Opportunités appuyées par une citation source",
                "points": points,
                "justification": f"{len(supported_opportunities)} opportunité(s) possède(nt) une preuve textuelle validée.",
            }
        )

    risk = min(100, risk)
    opportunity = min(75, opportunity)

    explanation = {
        "version": SCORING_VERSION,
        "event_code": event_code,
        "risk_breakdown": risk_breakdown,
        "opportunity_breakdown": opportunity_breakdown,
        "opportunity_scope": (
            "Potentiel générique LegalTech. Ce score n'est pas encore une recommandation "
            "d'investissement UGFS et doit être confirmé avec les priorités sectorielles, "
            "la taille cible et les critères d'éligibilité."
        ),
        "ocr_used_in_business_scores": False,
    }
    return risk, opportunity, explanation


def ml_predict_if_available(
    features: dict[str, Any],
    fallback_risk: int,
    fallback_opp: int,
) -> tuple[int, int, str]:
    """Use only a trained model explicitly certified for scoring v5."""
    risk_model_path = MODELS_DIR / "risk_regressor.joblib"
    opp_model_path = MODELS_DIR / "opportunity_regressor.joblib"
    feature_order_path = MODELS_DIR / "feature_order.joblib"
    metadata_path = MODELS_DIR / "model_metadata.joblib"

    required_paths = [
        risk_model_path,
        opp_model_path,
        feature_order_path,
        metadata_path,
    ]
    if not all(path.exists() for path in required_paths):
        return fallback_risk, fallback_opp, "baseline_rules_v6"

    metadata = joblib.load(metadata_path)
    if not isinstance(metadata, dict) or metadata.get("scoring_version") != SCORING_VERSION:
        return fallback_risk, fallback_opp, "baseline_rules_v6"

    feature_order = joblib.load(feature_order_path)
    X = [[features.get(key, 0) for key in feature_order]]
    risk_model = joblib.load(risk_model_path)
    opportunity_model = joblib.load(opp_model_path)

    risk = int(round(max(0, min(100, risk_model.predict(X)[0]))))
    opportunity = int(round(max(0, min(100, opportunity_model.predict(X)[0]))))
    return risk, opportunity, "ml_regression_v6"


def compute_confidence_breakdown(analysis: dict[str, Any]) -> dict[str, Any]:
    """Measure pipeline quality with factual-validation confidence caps.

    These values are quality indicators. They are not probabilities of legal
    truth and they never alter the business risk/opportunity scores.
    """
    ocr_quality = max(0.0, min(1.0, float(analysis.get("ocr_quality", 0.0))))
    json_valid = bool(analysis.get("json_valid", False))
    llm_confidence = max(
        0.0,
        min(0.95, float(analysis.get("niveau_confiance_llm", 0.0))),
    )

    company_known = str(analysis.get("societe", "")).strip() not in {"", "À vérifier"}
    event_known = str(analysis.get("type_evenement_code", "")).strip() not in {"", "AUTRE"}
    category_known = str(analysis.get("categorie", "")).strip() not in {"", "À classifier manuellement"}
    summary_present = bool(str(analysis.get("resume", "")).strip())
    completeness = sum([company_known, event_known, category_known, summary_present]) / 4

    risk_items = analysis.get("risques_detectes", [])
    risk_evidence = analysis.get("risques_avec_preuves", [])
    opp_items = analysis.get("opportunites_detectees", [])
    opp_evidence = analysis.get("opportunites_avec_preuves", [])

    total_claims = (len(risk_items) if isinstance(risk_items, list) else 0) + (
        len(opp_items) if isinstance(opp_items, list) else 0
    )
    supported_claims = (len(risk_evidence) if isinstance(risk_evidence, list) else 0) + (
        len(opp_evidence) if isinstance(opp_evidence, list) else 0
    )

    evidence_coverage: float | None
    if total_claims == 0:
        evidence_coverage = None
        evidence_component = 0.75
        evidence_status = "N/A — aucune affirmation risque/opportunité"
    else:
        evidence_coverage = min(1.0, supported_claims / total_claims)
        evidence_component = evidence_coverage
        evidence_status = f"{evidence_coverage:.3f}"

    factual = analysis.get("validation_factuelle", {})
    factual_status = str(factual.get("status", "UNKNOWN")) if isinstance(factual, dict) else "UNKNOWN"
    financial_status = str(factual.get("financial_status", "NOT_APPLICABLE")) if isinstance(factual, dict) else "NOT_APPLICABLE"
    corrections = factual.get("corrections", []) if isinstance(factual, dict) else []
    issues = factual.get("issues", []) if isinstance(factual, dict) else []

    major_fields = {"type_evenement_code", "societe", "resume"}
    major_corrections = sum(
        1
        for item in corrections
        if isinstance(item, dict) and item.get("field") in major_fields
    )
    validation_factor = max(
        0.40,
        1.0 - 0.10 * len(issues) - 0.06 * major_corrections,
    )

    interpretation = (
        0.30 * completeness
        + 0.20 * (1.0 if json_valid else 0.0)
        + 0.20 * llm_confidence
        + 0.15 * evidence_component
        + 0.15 * validation_factor
    )

    # The LLM interpretation must never display perfect certainty.
    confidence_cap = 0.95
    cap_reason = "Plafond général de confiance d'interprétation"

    if factual_status == "WARNING":
        confidence_cap = min(confidence_cap, 0.75)
        cap_reason = "Validation factuelle en avertissement"
    elif factual_status == "FAIL":
        confidence_cap = min(confidence_cap, 0.50)
        cap_reason = "Échec de validation factuelle"

    if financial_status in {"UNVERIFIED", "MISMATCH"}:
        financial_cap = 0.80 if financial_status == "UNVERIFIED" else 0.70
        if financial_cap < confidence_cap:
            confidence_cap = financial_cap
            cap_reason = f"Contrôle financier: {financial_status}"

    interpretation = max(0.0, min(confidence_cap, interpretation))
    overall = 0.50 * ocr_quality + 0.50 * interpretation

    return {
        "confiance_extraction": round(ocr_quality, 3),
        "confiance_interpretation": round(interpretation, 3),
        "confiance_globale": round(max(0.0, min(0.95, overall)), 3),
        "evidence_coverage": None if evidence_coverage is None else round(evidence_coverage, 3),
        "evidence_status": evidence_status,
        "validation_factor": round(validation_factor, 3),
        "confidence_cap": round(confidence_cap, 3),
        "confidence_cap_reason": cap_reason,
        "factual_status": factual_status,
        "financial_status": financial_status,
        "json_valid": json_valid,
    }


def score_analysis(analysis: dict[str, Any], text: str) -> dict[str, Any]:
    """Correct facts, calculate scores and attach an auditable explanation."""
    analysis = validate_and_correct_analysis(analysis, text)
    features = extract_features(analysis, text)

    base_risk, base_opportunity, explanation = baseline_scores(analysis, text)
    risk, opportunity, method = ml_predict_if_available(
        features,
        base_risk,
        base_opportunity,
    )
    confidence = compute_confidence_breakdown(analysis)

    risk_level = level_from_score(risk)
    opportunity_level = level_from_score(
        opportunity,
        critical_label="Très élevé",
    )

    derived_risk = analysis.get("evaluation_risque_derivee")
    if isinstance(derived_risk, dict):
        derived_risk = dict(derived_risk)
        derived_risk["score"] = risk
        derived_risk["niveau"] = risk_level
        analysis["evaluation_risque_derivee"] = derived_risk

    derived_opportunity = analysis.get("opportunite_potentielle_derivee")
    if isinstance(derived_opportunity, dict) and derived_opportunity:
        derived_opportunity = dict(derived_opportunity)
        derived_opportunity["score"] = opportunity
        derived_opportunity["niveau"] = opportunity_level
        analysis["opportunite_potentielle_derivee"] = derived_opportunity

    analysis.update(
        {
            "score_risque": risk,
            "niveau_risque": risk_level,
            "score_opportunite": opportunity,
            "niveau_opportunite": opportunity_level,
            "niveau_confiance": confidence["confiance_globale"],
            "confiance_extraction": confidence["confiance_extraction"],
            "confiance_interpretation": confidence["confiance_interpretation"],
            "couverture_preuves": confidence["evidence_coverage"],
            "statut_couverture_preuves": confidence["evidence_status"],
            "plafond_confiance_interpretation": confidence["confidence_cap"],
            "raison_plafond_confiance": confidence["confidence_cap_reason"],
            "scoring_method": method,
            "scoring_version": SCORING_VERSION,
            "score_breakdown": explanation,
            "features": features,
        }
    )
    return analysis
