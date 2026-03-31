"""SageMaker training script for churn prediction model."""

import os
import json
import logging
import argparse
import numpy as np
import pandas as pd
import joblib
from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_score
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.metrics import roc_auc_score, classification_report, confusion_matrix
from xgboost import XGBClassifier

from churn_prediction.generate_data import generate_churn_data

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

CATEGORICAL_COLS = ["gender", "partner", "dependents", "phone_service", "internet_service",
                    "online_security", "tech_support", "streaming_tv", "streaming_movies",
                    "contract", "paperless_billing", "payment_method"]
NUMERIC_COLS = ["senior_citizen", "tenure", "monthly_charges", "total_charges",
                "tech_support_calls", "avg_monthly_usage_gb", "contract_renewals",
                "last_interaction_days", "satisfaction_score"]
TARGET = "churn"


def prepare_features(df: pd.DataFrame, label_encoders=None, scaler=None, fit=True):
    X = df.drop(columns=[TARGET, "customer_id"], errors="ignore").copy()

    if label_encoders is None:
        label_encoders = {}
    if fit:
        for col in CATEGORICAL_COLS:
            if col in X.columns:
                le = LabelEncoder()
                X[col] = le.fit_transform(X[col].astype(str))
                label_encoders[col] = le
    else:
        for col in CATEGORICAL_COLS:
            if col in X.columns and col in label_encoders:
                le = label_encoders[col]
                X[col] = X[col].astype(str).map(lambda x: le.transform([x])[0] if x in le.classes_ else -1)

    if scaler is None:
        scaler = StandardScaler()
    numeric_present = [c for c in NUMERIC_COLS if c in X.columns]
    if fit:
        X[numeric_present] = scaler.fit_transform(X[numeric_present])
    else:
        X[numeric_present] = scaler.transform(X[numeric_present])

    y = df[TARGET].values if TARGET in df.columns else None
    return X, y, label_encoders, scaler


def train_model(data_path=None, model_dir="model", n_estimators=300, max_depth=6,
                learning_rate=0.1, test_size=0.2, seed=42):
    if data_path and os.path.exists(data_path):
        df = pd.read_csv(data_path)
    else:
        df = generate_churn_data(5000, seed=seed)

    logger.info(f"Dataset: {len(df)} rows, churn rate: {df['churn'].mean():.2%}")

    X, y, label_encoders, scaler = prepare_features(df, fit=True)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=test_size, random_state=seed, stratify=y)

    neg, pos = (y_train == 0).sum(), (y_train == 1).sum()
    scale_pos_weight = neg / pos if pos > 0 else 1.0

    model = XGBClassifier(
        n_estimators=n_estimators, max_depth=max_depth, learning_rate=learning_rate,
        subsample=0.8, colsample_bytree=0.8, scale_pos_weight=scale_pos_weight,
        random_state=seed, eval_metric="auc", use_label_encoder=False,
    )
    model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=50)

    y_prob = model.predict_proba(X_test)[:, 1]
    y_pred = model.predict(X_test)
    auc = roc_auc_score(y_test, y_prob)
    logger.info(f"AUC-ROC: {auc:.4f}")
    logger.info(f"\n{classification_report(y_test, y_pred)}")

    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=seed)
    cv_scores = cross_val_score(model, X, y, cv=cv, scoring="roc_auc")
    logger.info(f"CV AUC: {cv_scores.mean():.4f} +/- {cv_scores.std():.4f}")

    importance = dict(zip(X.columns, model.feature_importances_))
    top = sorted(importance.items(), key=lambda x: x[1], reverse=True)[:10]
    logger.info("Top features: " + ", ".join(f"{k}: {v:.4f}" for k, v in top))

    os.makedirs(model_dir, exist_ok=True)
    joblib.dump(model, os.path.join(model_dir, "model.joblib"))
    joblib.dump(label_encoders, os.path.join(model_dir, "label_encoders.joblib"))
    joblib.dump(scaler, os.path.join(model_dir, "scaler.joblib"))
    joblib.dump(list(X.columns), os.path.join(model_dir, "feature_names.joblib"))

    metrics = {
        "auc_roc": round(auc, 4), "cv_auc_mean": round(cv_scores.mean(), 4),
        "classification_report": classification_report(y_test, y_pred, output_dict=True),
        "confusion_matrix": confusion_matrix(y_test, y_pred).tolist(),
        "feature_importance": {k: round(float(v), 4) for k, v in top},
    }
    with open(os.path.join(model_dir, "metrics.json"), "w") as f:
        json.dump(metrics, f, indent=2)

    return model, metrics


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-path", type=str, default=None)
    parser.add_argument("--model-dir", type=str, default=os.environ.get("SM_MODEL_DIR", "model"))
    args = parser.parse_args()
    train_model(data_path=args.data_path, model_dir=args.model_dir)
