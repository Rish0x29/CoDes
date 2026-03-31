"""Comprehensive model evaluation for churn prediction."""

import os
import json
import numpy as np
import pandas as pd
import joblib
from sklearn.metrics import (
    roc_auc_score, roc_curve, precision_recall_curve, average_precision_score,
    classification_report, confusion_matrix,
)
from sklearn.model_selection import train_test_split
from churn_prediction.train import prepare_features
from churn_prediction.generate_data import generate_churn_data


def evaluate(model_dir="model", data_path=None, output_dir="evaluation"):
    os.makedirs(output_dir, exist_ok=True)
    model = joblib.load(os.path.join(model_dir, "model.joblib"))
    label_encoders = joblib.load(os.path.join(model_dir, "label_encoders.joblib"))
    scaler = joblib.load(os.path.join(model_dir, "scaler.joblib"))

    df = pd.read_csv(data_path) if data_path and os.path.exists(data_path) else generate_churn_data(2000, seed=99)

    X, y, _, _ = prepare_features(df, label_encoders=label_encoders, scaler=scaler, fit=False)
    y_prob = model.predict_proba(X)[:, 1]
    y_pred = model.predict(X)

    auc = roc_auc_score(y, y_prob)
    fpr, tpr, _ = roc_curve(y, y_prob)
    precision, recall, _ = precision_recall_curve(y, y_prob)
    avg_precision = average_precision_score(y, y_prob)
    cm = confusion_matrix(y, y_pred)

    # Cohort analysis
    cohorts = {}
    if "contract" in df.columns:
        for contract_type in df["contract"].unique():
            mask = df["contract"] == contract_type
            if mask.sum() > 10:
                cohorts[f"contract_{contract_type}"] = {
                    "count": int(mask.sum()),
                    "actual_churn_rate": round(float(y[mask].mean()), 4),
                    "predicted_churn_rate": round(float(y_prob[mask].mean()), 4),
                    "auc": round(float(roc_auc_score(y[mask], y_prob[mask])), 4) if len(np.unique(y[mask])) > 1 else None,
                }

    if "tenure" in df.columns:
        tenure_bins = pd.cut(df["tenure"], bins=[0, 6, 12, 24, 48, 72], labels=["0-6m", "6-12m", "1-2y", "2-4y", "4y+"])
        for bucket in tenure_bins.unique():
            if pd.notna(bucket):
                mask = tenure_bins == bucket
                if mask.sum() > 10:
                    cohorts[f"tenure_{bucket}"] = {
                        "count": int(mask.sum()),
                        "actual_churn_rate": round(float(y[mask].mean()), 4),
                        "predicted_churn_rate": round(float(y_prob[mask].mean()), 4),
                    }

    feature_importance = dict(zip(X.columns, model.feature_importances_))

    evaluation = {
        "auc_roc": round(auc, 4),
        "average_precision": round(avg_precision, 4),
        "confusion_matrix": cm.tolist(),
        "classification_report": classification_report(y, y_pred, output_dict=True),
        "feature_importance": {k: round(float(v), 4) for k, v in
                               sorted(feature_importance.items(), key=lambda x: x[1], reverse=True)},
        "cohort_analysis": cohorts,
        "n_samples": len(y),
        "churn_rate": round(float(y.mean()), 4),
    }

    with open(os.path.join(output_dir, "evaluation.json"), "w") as f:
        json.dump(evaluation, f, indent=2)

    print(f"AUC-ROC: {auc:.4f} | Avg Precision: {avg_precision:.4f}")
    return evaluation


if __name__ == "__main__":
    evaluate()
