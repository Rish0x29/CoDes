"""Model evaluation with detailed metrics and feature importance."""

import json
import logging
import numpy as np
import pandas as pd
import joblib
from sklearn.metrics import (
    roc_auc_score, roc_curve, precision_recall_curve,
    average_precision_score, classification_report, confusion_matrix,
)
from sklearn.model_selection import train_test_split

from credit_risk.preprocessing import preprocess_data
from credit_risk.generate_sample_data import generate_credit_data

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def evaluate_model(model_dir: str = "model", data_path: str = None, output_dir: str = "evaluation"):
    import os
    os.makedirs(output_dir, exist_ok=True)

    model = joblib.load(os.path.join(model_dir, "model.joblib"))
    preprocessor = joblib.load(os.path.join(model_dir, "preprocessor.joblib"))

    if data_path and os.path.exists(data_path):
        df = pd.read_csv(data_path)
    else:
        df = generate_credit_data(2000, seed=99)

    X, y, _, feature_names = preprocess_data(df, preprocessor=preprocessor, fit=False)

    y_prob = model.predict_proba(X)[:, 1]
    y_pred = model.predict(X)

    # ROC curve data
    fpr, tpr, roc_thresholds = roc_curve(y, y_prob)
    auc_roc = roc_auc_score(y, y_prob)

    # Precision-Recall curve
    precision, recall, pr_thresholds = precision_recall_curve(y, y_prob)
    avg_precision = average_precision_score(y, y_prob)

    # Confusion matrix
    cm = confusion_matrix(y, y_pred)
    report = classification_report(y, y_pred, output_dict=True)

    # Feature importance
    importance = dict(zip(feature_names, model.feature_importances_))
    sorted_importance = sorted(importance.items(), key=lambda x: x[1], reverse=True)

    # Threshold analysis
    threshold_analysis = []
    for threshold in np.arange(0.1, 0.9, 0.05):
        y_t = (y_prob >= threshold).astype(int)
        cm_t = confusion_matrix(y, y_t)
        tn, fp, fn, tp = cm_t.ravel()
        threshold_analysis.append({
            "threshold": round(threshold, 2),
            "precision": round(tp / (tp + fp), 4) if (tp + fp) > 0 else 0,
            "recall": round(tp / (tp + fn), 4) if (tp + fn) > 0 else 0,
            "false_positive_rate": round(fp / (fp + tn), 4) if (fp + tn) > 0 else 0,
            "accuracy": round((tp + tn) / (tp + tn + fp + fn), 4),
        })

    evaluation = {
        "auc_roc": round(auc_roc, 4),
        "average_precision": round(avg_precision, 4),
        "confusion_matrix": cm.tolist(),
        "classification_report": report,
        "feature_importance": {k: round(float(v), 4) for k, v in sorted_importance},
        "threshold_analysis": threshold_analysis,
        "roc_curve": {"fpr": fpr.tolist()[:50], "tpr": tpr.tolist()[:50]},
        "n_samples": len(y),
        "default_rate": round(float(y.mean()), 4),
    }

    with open(os.path.join(output_dir, "evaluation.json"), "w") as f:
        json.dump(evaluation, f, indent=2)

    logger.info(f"AUC-ROC: {auc_roc:.4f}")
    logger.info(f"Average Precision: {avg_precision:.4f}")
    logger.info(f"Evaluation saved to {output_dir}/")
    return evaluation


if __name__ == "__main__":
    evaluate_model()
