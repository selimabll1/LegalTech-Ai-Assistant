from modules.scoring_engine import score_analysis


def test_scoring_capital_event():
    analysis = {
        "type_evenement": "Augmentation de capital",
        "categorie": "Capital",
        "societe": "ABC",
        "resume": "Test",
        "action_recommandee": "Valider",
        "ocr_quality": 0.9,
        "niveau_confiance_llm": 0.8,
        "json_valid": True,
    }
    result = score_analysis(analysis, "augmentation du capital social de 2 millions TND")
    assert result["score_risque"] >= 20
    assert result["score_opportunite"] >= 20
    assert 0 <= result["niveau_confiance"] <= 1
