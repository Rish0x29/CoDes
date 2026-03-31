"""Batch scoring - score all customers and assign risk tiers."""

import os
import json
import logging
import numpy as np
import pandas as pd
import joblib

from churn_prediction.train import prepare_features
from churn_prediction.generate_data import generate_churn_data

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def load_model(model_dir: str = "model"):
    model = joblib.load(os.path.join(model_dir, "model.joblib"))
    label_encoders = joblib.load(os.path.join(model_dir, "label_encoders.joblib"))
    scaler = joblib.load(os.path.join(model_dir, "scaler.joblib"))
    return model, label_encoders, scaler


def score_customers(data_path: str = None, model_dir: str = "model", output_path: str = "scored_customers.csv"):
    model, label_encoders, scaler = load_model(model_dir)

    if data_path and os.path.exists(data_path):
        df = pd.read_csv(data_path)
    else:
        df = generate_churn_data(5000, seed=99)

    customer_ids = df["customer_id"].values if "customer_id" in df.columns else range(len(df))

    X, _, _, _ = prepare_features(df, label_encoders=label_encoders, scaler=scaler, fit=False)
    probabilities = model.predict_proba(X)[:, 1]

    # Assign risk tiers
    risk_tiers = np.where(probabilities < 0.3, "LOW",
                 np.where(probabilities < 0.6, "MEDIUM", "HIGH"))

    # Get feature importance per customer (approximate using feature contributions)
    feature_names = list(X.columns)
    top_risk_factors = []
    for i in range(len(X)):
        row_values = X.iloc[i].values
        contributions = row_values * model.feature_importances_
        top_indices = np.argsort(np.abs(contributions))[-3:][::-1]
        factors = [{"feature": feature_names[j], "contribution": round(float(contributions[j]), 4)}
                   for j in top_indices]
        top_risk_factors.append(json.dumps(factors))

    results = pd.DataFrame({
        "customer_id": customer_ids,
        "churn_probability": np.round(probabilities, 4),
        "risk_tier": risk_tiers,
        "churn_score": np.round(probabilities * 100, 1),
        "top_risk_factors": top_risk_factors,
    })

    # Add original features for context
    context_cols = ["tenure", "contract", "monthly_charges", "internet_service", "satisfaction_score"]
    for col in context_cols:
        if col in df.columns:
            results[col] = df[col].values

    results = results.sort_values("churn_probability", ascending=False)
    results.to_csv(output_path, index=False)

    # Summary stats
    tier_counts = results["risk_tier"].value_counts()
    logger.info(f"Scored {len(results)} customers")
    logger.info(f"Risk distribution:\n{tier_counts}")
    logger.info(f"Avg churn probability: {probabilities.mean():.2%}")
    logger.info(f"Results saved to {output_path}")

    return results


if __name__ == "__main__":
    score_customers()
