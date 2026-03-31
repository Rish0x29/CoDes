"""SageMaker training script for credit risk model."""

import os
import json
import logging
import argparse
import numpy as np
import pandas as pd
import joblib
from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_score
from sklearn.metrics import (
    roc_auc_score, classification_report, confusion_matrix,
    precision_recall_curve, average_precision_score,
)
from xgboost import XGBClassifier

from credit_risk.preprocessing import preprocess_data, save_preprocessor
from credit_risk.generate_sample_data import generate_credit_data

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def train_model(
    data_path: str = None,
    model_dir: str = "model",
    n_estimators: int = 300,
    max_depth: int = 6,
    learning_rate: float = 0.1,
    subsample: float = 0.8,
    colsample_bytree: float = 0.8,
    min_child_weight: int = 3,
    gamma: float = 0.1,
    reg_alpha: float = 0.1,
    reg_lambda: float = 1.0,
    scale_pos_weight: float = None,
    test_size: float = 0.2,
    random_state: int = 42,
):
    # Load data
    if data_path and os.path.exists(data_path):
        df = pd.read_csv(data_path)
        logger.info(f"Loaded {len(df)} records from {data_path}")
    else:
        logger.info("No data path provided, generating synthetic data")
        df = generate_credit_data(5000, seed=random_state)

    logger.info(f"Default rate: {df['default'].mean():.2%}")

    # Preprocess
    X, y, preprocessor, feature_names = preprocess_data(df, fit=True)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=random_state, stratify=y
    )
    logger.info(f"Train: {X_train.shape}, Test: {X_test.shape}")

    # Auto-calculate scale_pos_weight if not provided
    if scale_pos_weight is None:
        neg_count = (y_train == 0).sum()
        pos_count = (y_train == 1).sum()
        scale_pos_weight = neg_count / pos_count if pos_count > 0 else 1.0
        logger.info(f"Auto scale_pos_weight: {scale_pos_weight:.2f}")

    # Train XGBoost
    model = XGBClassifier(
        n_estimators=n_estimators, max_depth=max_depth, learning_rate=learning_rate,
        subsample=subsample, colsample_bytree=colsample_bytree,
        min_child_weight=min_child_weight, gamma=gamma,
        reg_alpha=reg_alpha, reg_lambda=reg_lambda,
        scale_pos_weight=scale_pos_weight, random_state=random_state,
        eval_metric="auc", use_label_encoder=False,
    )

    model.fit(
        X_train, y_train,
        eval_set=[(X_test, y_test)],
        verbose=50,
    )

    # Evaluate
    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1]
    auc_roc = roc_auc_score(y_test, y_prob)
    avg_precision = average_precision_score(y_test, y_prob)
    cm = confusion_matrix(y_test, y_pred)
    report = classification_report(y_test, y_pred, output_dict=True)

    logger.info(f"\nAUC-ROC: {auc_roc:.4f}")
    logger.info(f"Average Precision: {avg_precision:.4f}")
    logger.info(f"Confusion Matrix:\n{cm}")
    logger.info(f"\n{classification_report(y_test, y_pred)}")

    # Cross-validation
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=random_state)
    cv_scores = cross_val_score(model, X, y, cv=cv, scoring="roc_auc")
    logger.info(f"CV AUC-ROC: {cv_scores.mean():.4f} +/- {cv_scores.std():.4f}")

    # Feature importance
    importance = dict(zip(feature_names, model.feature_importances_))
    top_features = sorted(importance.items(), key=lambda x: x[1], reverse=True)[:15]
    logger.info("Top 15 features:")
    for name, imp in top_features:
        logger.info(f"  {name}: {imp:.4f}")

    # Save artifacts
    os.makedirs(model_dir, exist_ok=True)
    joblib.dump(model, os.path.join(model_dir, "model.joblib"))
    save_preprocessor(preprocessor, os.path.join(model_dir, "preprocessor.joblib"))

    metrics = {
        "auc_roc": round(auc_roc, 4),
        "average_precision": round(avg_precision, 4),
        "cv_auc_mean": round(cv_scores.mean(), 4),
        "cv_auc_std": round(cv_scores.std(), 4),
        "classification_report": report,
        "confusion_matrix": cm.tolist(),
        "feature_importance": {k: round(float(v), 4) for k, v in top_features},
    }
    with open(os.path.join(model_dir, "metrics.json"), "w") as f:
        json.dump(metrics, f, indent=2)

    logger.info(f"Model saved to {model_dir}/")
    return model, preprocessor, metrics


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-path", type=str, default=None)
    parser.add_argument("--model-dir", type=str, default=os.environ.get("SM_MODEL_DIR", "model"))
    parser.add_argument("--n-estimators", type=int, default=300)
    parser.add_argument("--max-depth", type=int, default=6)
    parser.add_argument("--learning-rate", type=float, default=0.1)
    args = parser.parse_args()

    train_model(
        data_path=args.data_path,
        model_dir=args.model_dir,
        n_estimators=args.n_estimators,
        max_depth=args.max_depth,
        learning_rate=args.learning_rate,
    )
