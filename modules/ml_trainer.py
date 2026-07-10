from pathlib import Path
import pandas as pd
import joblib
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import cross_val_score
from config import TRAINING_DATASET_PATH, MODELS_DIR

FEATURE_COLUMNS = [
    "has_liquidation",
    "has_collective_procedure",
    "has_capital_event",
    "has_ma_asset_sale",
    "has_governance",
    "has_shareholder_change",
    "has_deadline",
    "mentions_amount",
    "ocr_quality",
    "llm_confidence",
    "json_valid",
]


def train_scoring_models(model_type: str = "linear") -> dict:
    """Train risk/opportunity regressors when enough corrected examples exist.

    This is optional for later phases. The MVP can run without trained models.
    Expected training file: data/feedback/training_dataset.xlsx
    Required target columns:
    - Score_Risque_Corrigé
    - Score_Opportunité_Corrigé
    Required feature columns: see FEATURE_COLUMNS.
    """
    if not TRAINING_DATASET_PATH.exists():
        return {"status": "missing_training_dataset", "path": str(TRAINING_DATASET_PATH)}

    df = pd.read_excel(TRAINING_DATASET_PATH)
    missing = [c for c in FEATURE_COLUMNS if c not in df.columns]
    targets = ["Score_Risque_Corrigé", "Score_Opportunité_Corrigé"]
    missing += [c for c in targets if c not in df.columns]
    if missing:
        return {"status": "missing_columns", "missing": missing}

    df = df.dropna(subset=targets)
    if len(df) < 30:
        return {"status": "not_enough_data", "rows": len(df), "minimum_recommended": 30}

    X = df[FEATURE_COLUMNS].fillna(0)
    y_risk = df["Score_Risque_Corrigé"].astype(float)
    y_opp = df["Score_Opportunité_Corrigé"].astype(float)

    Model = LinearRegression if model_type == "linear" else RandomForestRegressor
    risk_model = Model()
    opp_model = Model()
    risk_model.fit(X, y_risk)
    opp_model.fit(X, y_opp)

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(risk_model, MODELS_DIR / "risk_regressor.joblib")
    joblib.dump(opp_model, MODELS_DIR / "opportunity_regressor.joblib")
    joblib.dump(FEATURE_COLUMNS, MODELS_DIR / "feature_order.joblib")

    return {"status": "trained", "rows": len(df), "model_type": model_type, "features": FEATURE_COLUMNS}


if __name__ == "__main__":
    print(train_scoring_models())
