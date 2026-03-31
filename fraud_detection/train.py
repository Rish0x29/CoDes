"""Train fraud detection model - Isolation Forest + XGBoost ensemble."""

import os
import json
import logging
import argparse
import numpy as np
import pandas as pd
import joblib
from sklearn.ensemble import IsolationForest
from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_score
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.metrics import (
    roc_auc_score, classification_report, confusion_matrix,
    precision_recall_curve, average_precision_score,
)
from xgboost import XGBClassifier

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def generate_fraud_data(n_samples: int = 10000, fraud_rate: float = 0.03, seed: int = 42) -> pd.DataFrame:
    """Generate realistic synthetic transaction data with fraud labels."""
    rng = np.random.RandomState(seed)

    n_fraud = int(n_samples * fraud_rate)
    n_legit = n_samples - n_fraud

    # Legitimate transactions
    legit = pd.DataFrame({
        "amount": rng.lognormal(mean=3.5, sigma=1.2, size=n_legit).clip(0.5, 5000),
        "hour_of_day": rng.choice(range(24), size=n_legit, p=_hour_probs(rng)),
        "day_of_week": rng.choice(range(7), size=n_legit),
        "merchant_category": rng.choice(["grocery", "gas", "restaurant", "retail", "online", "travel", "entertainment"], size=n_legit),
        "distance_from_home": rng.exponential(scale=15, size=n_legit).clip(0, 500),
        "distance_from_last_txn": rng.exponential(scale=8, size=n_legit).clip(0, 300),
        "txn_count_1h": rng.poisson(lam=1.5, size=n_legit),
        "txn_count_24h": rng.poisson(lam=5, size=n_legit),
        "avg_amount_30d": rng.lognormal(mean=3.5, sigma=0.8, size=n_legit).clip(10, 3000),
        "card_present": rng.choice([0, 1], size=n_legit, p=[0.25, 0.75]),
        "international": rng.choice([0, 1], size=n_legit, p=[0.95, 0.05]),
        "is_fraud": 0,
    })

    # Fraudulent transactions
    fraud = pd.DataFrame({
        "amount": rng.lognormal(mean=5.0, sigma=1.5, size=n_fraud).clip(50, 25000),
        "hour_of_day": rng.choice(range(24), size=n_fraud, p=_fraud_hour_probs(rng)),
        "day_of_week": rng.choice(range(7), size=n_fraud),
        "merchant_category": rng.choice(["online", "electronics", "jewelry", "travel", "wire_transfer"], size=n_fraud),
        "distance_from_home": rng.exponential(scale=100, size=n_fraud).clip(0, 2000),
        "distance_from_last_txn": rng.exponential(scale=80, size=n_fraud).clip(0, 1500),
        "txn_count_1h": rng.poisson(lam=5, size=n_fraud).clip(0, 20),
        "txn_count_24h": rng.poisson(lam=15, size=n_fraud).clip(0, 50),
        "avg_amount_30d": rng.lognormal(mean=3.5, sigma=0.8, size=n_fraud).clip(10, 3000),
        "card_present": rng.choice([0, 1], size=n_fraud, p=[0.70, 0.30]),
        "international": rng.choice([0, 1], size=n_fraud, p=[0.60, 0.40]),
        "is_fraud": 1,
    })

    df = pd.concat([legit, fraud], ignore_index=True)
    df = df.sample(frac=1, random_state=seed).reset_index(drop=True)
    df["transaction_id"] = [f"TXN-{i:08d}" for i in range(len(df))]
    df["customer_id"] = [f"CUST-{rng.randint(1000, 9999):04d}" for _ in range(len(df))]

    # Derived features
    df["amount_vs_avg"] = df["amount"] / df["avg_amount_30d"].clip(lower=1)
    df["velocity_1h"] = df["txn_count_1h"] * df["amount"]
    df["is_night"] = ((df["hour_of_day"] >= 23) | (df["hour_of_day"] <= 5)).astype(int)
    df["is_weekend"] = (df["day_of_week"] >= 5).astype(int)
    df["high_amount_flag"] = (df["amount"] > df["avg_amount_30d"] * 3).astype(int)

    return df


def _hour_probs(rng):
    p = np.array([0.01, 0.005, 0.005, 0.005, 0.005, 0.01, 0.02, 0.04, 0.06, 0.07,
                  0.07, 0.08, 0.08, 0.07, 0.06, 0.06, 0.06, 0.06, 0.05, 0.05,
                  0.04, 0.03, 0.02, 0.015])
    return p / p.sum()


def _fraud_hour_probs(rng):
    p = np.array([0.06, 0.06, 0.07, 0.07, 0.06, 0.05, 0.03, 0.02, 0.02, 0.02,
                  0.03, 0.03, 0.04, 0.04, 0.04, 0.04, 0.04, 0.04, 0.04, 0.04,
                  0.04, 0.04, 0.05, 0.06])
    return p / p.sum()


FEATURE_COLS = [
    "amount", "hour_of_day", "day_of_week", "distance_from_home",
    "distance_from_last_txn", "txn_count_1h", "txn_count_24h", "avg_amount_30d",
    "card_present", "international", "amount_vs_avg", "velocity_1h",
    "is_night", "is_weekend", "high_amount_flag",
]

CATEGORICAL_COLS = ["merchant_category"]


def prepare_features(df: pd.DataFrame, label_encoder=None, scaler=None, fit=True):
    X = df.copy()

    if label_encoder is None:
        label_encoder = LabelEncoder()
    if fit:
        X["merchant_encoded"] = label_encoder.fit_transform(X["merchant_category"].astype(str))
    else:
        X["merchant_encoded"] = X["merchant_category"].astype(str).map(
            lambda x: label_encoder.transform([x])[0] if x in label_encoder.classes_ else -1)

    features = FEATURE_COLS + ["merchant_encoded"]
    X_features = X[features].values

    if scaler is None:
        scaler = StandardScaler()
    if fit:
        X_scaled = scaler.fit_transform(X_features)
    else:
        X_scaled = scaler.transform(X_features)

    y = df["is_fraud"].values if "is_fraud" in df.columns else None
    return X_scaled, y, label_encoder, scaler, features


def train_model(data_path=None, model_dir="model", n_estimators=300, seed=42):
    if data_path and os.path.exists(data_path):
        df = pd.read_csv(data_path)
    else:
        df = generate_fraud_data(10000, seed=seed)

    logger.info(f"Dataset: {len(df)} transactions, fraud rate: {df['is_fraud'].mean():.2%}")

    X, y, label_encoder, scaler, feature_names = prepare_features(df, fit=True)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=seed, stratify=y)

    # 1. Isolation Forest (anomaly scores)
    iso_forest = IsolationForest(n_estimators=200, contamination=0.03, random_state=seed, n_jobs=-1)
    iso_forest.fit(X_train)
    iso_train_scores = -iso_forest.score_samples(X_train).reshape(-1, 1)
    iso_test_scores = -iso_forest.score_samples(X_test).reshape(-1, 1)

    # 2. XGBoost with anomaly score as extra feature
    X_train_aug = np.hstack([X_train, iso_train_scores])
    X_test_aug = np.hstack([X_test, iso_test_scores])

    neg, pos = (y_train == 0).sum(), (y_train == 1).sum()
    scale_pos_weight = neg / pos if pos > 0 else 1.0

    xgb_model = XGBClassifier(
        n_estimators=n_estimators, max_depth=6, learning_rate=0.1,
        subsample=0.8, colsample_bytree=0.8, scale_pos_weight=scale_pos_weight,
        random_state=seed, eval_metric="auc", use_label_encoder=False,
    )
    xgb_model.fit(X_train_aug, y_train, eval_set=[(X_test_aug, y_test)], verbose=50)

    # Evaluate
    y_prob = xgb_model.predict_proba(X_test_aug)[:, 1]
    y_pred = xgb_model.predict(X_test_aug)
    auc = roc_auc_score(y_test, y_prob)
    avg_precision = average_precision_score(y_test, y_prob)

    logger.info(f"AUC-ROC: {auc:.4f}")
    logger.info(f"Average Precision: {avg_precision:.4f}")
    logger.info(f"\n{classification_report(y_test, y_pred)}")

    # Save
    os.makedirs(model_dir, exist_ok=True)
    joblib.dump(xgb_model, os.path.join(model_dir, "xgb_model.joblib"))
    joblib.dump(iso_forest, os.path.join(model_dir, "iso_forest.joblib"))
    joblib.dump(scaler, os.path.join(model_dir, "scaler.joblib"))
    joblib.dump(label_encoder, os.path.join(model_dir, "label_encoder.joblib"))
    joblib.dump(feature_names, os.path.join(model_dir, "feature_names.joblib"))

    metrics = {
        "auc_roc": round(auc, 4),
        "average_precision": round(avg_precision, 4),
        "confusion_matrix": confusion_matrix(y_test, y_pred).tolist(),
        "classification_report": classification_report(y_test, y_pred, output_dict=True),
        "feature_importance": {name: round(float(imp), 4) for name, imp in
                               sorted(zip(feature_names + ["anomaly_score"], xgb_model.feature_importances_),
                                      key=lambda x: x[1], reverse=True)[:10]},
    }
    with open(os.path.join(model_dir, "metrics.json"), "w") as f:
        json.dump(metrics, f, indent=2)

    logger.info(f"Models saved to {model_dir}/")
    return xgb_model, iso_forest, metrics


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-path", type=str, default=None)
    parser.add_argument("--model-dir", type=str, default=os.environ.get("SM_MODEL_DIR", "model"))
    args = parser.parse_args()
    train_model(data_path=args.data_path, model_dir=args.model_dir)
