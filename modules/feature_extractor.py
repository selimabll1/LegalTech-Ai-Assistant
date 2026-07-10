import re


def extract_features(analysis: dict, text: str) -> dict:
    """Create ML-ready features from LLM output + source text.

    These are intentionally simple for the MVP. When enough corrected rows exist,
    this function can be expanded with TF-IDF text features or embeddings.
    """
    event = (analysis.get("type_evenement") or "").lower()
    category = (analysis.get("categorie") or "").lower()
    all_text = f"{event} {category} {text[:7000]}".lower()

    return {
        "has_liquidation": int(any(w in all_text for w in ["liquidation", "dissolution anticipée", "radiation"])),
        "has_collective_procedure": int(any(w in all_text for w in ["procédure collective", "redressement", "faillite", "avis aux créanciers"])),
        "has_capital_event": int(any(w in all_text for w in ["augmentation de capital", "capital social", "réduction de capital"])),
        "has_ma_asset_sale": int(any(w in all_text for w in ["fusion", "acquisition", "cession", "vente d'actifs", "vente judiciaire", "apport"])),
        "has_governance": int(any(w in all_text for w in ["gérant", "dirigeant", "administrateur", "assemblée", "statutaire", "conseil"])),
        "has_shareholder_change": int(any(w in all_text for w in ["actionnaire", "actionnariat", "parts sociales", "cession de parts"])),
        "has_deadline": int(any(w in all_text for w in ["délai", "convocation", "audience", "créanciers", "opposition"])),
        "mentions_amount": int(bool(re.search(r"\b\d+[\s.,]*(tnd|dt|dinars?|mdt|millions?)\b", all_text))),
        "ocr_quality": float(analysis.get("ocr_quality", 0.7)),
        "llm_confidence": float(analysis.get("niveau_confiance_llm", 0.5)),
        "json_valid": int(bool(analysis.get("json_valid", True))),
    }
