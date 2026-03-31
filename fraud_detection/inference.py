"""SageMaker inference handler for fraud detection."""

import os
import json
import numpy as np
import joblib

model = None
iso_forest = None
scaler = None
label_encoder = None
feature_names = None


def model_fn(model_dir: str):
    global model, iso_forest, scaler, label_encoder, feature_names
    model = joblib.load(os.path.join(model_dir, "xgb_model.joblib"))
    iso_forest = joblib.load(os.path.join(model_dir, "iso_forest.joblib"))
    scaler = joblib.load(os.path.join(model_dir, "scaler.joblib"))
    label_encoder = joblib.load(os.path.join(model_dir, "label_encoder.joblib"))
    feature_names = joblib.load(os.path.join(model_dir, "feature_names.joblib"))
    return model


def input_fn(request_body: str, content_type: str = "application/json"):
    data = json.loads(request_body)
    if isinstance(data, dict):
        data = [data]
    return data


def predict_fn(input_data: list, model_obj):
    global iso_forest, scaler, label_encoder, feature_names

    from fraud_detection.train import FEATURE_COLS

    results = []
    for txn in input_data:
        features = []
        for col in FEATURE_COLS:
            features.append(float(txn.get(col, 0)))

        cat = txn.get("merchant_category", "other")
        if cat in label_encoder.classes_:
            encoded = label_encoder.transform([cat])[0]
        else:
            encoded = -1
        features.append(encoded)

        X = np.array([features])
        X_scaled = scaler.transform(X)
        anomaly_score = -iso_forest.score_samples(X_scaled).reshape(-1, 1)
        X_aug = np.hstack([X_scaled, anomaly_score])

        prob = float(model_obj.predict_proba(X_aug)[0, 1])
        results.append({
            "fraud_probability": round(prob, 4),
            "is_fraud": prob >= 0.7,
            "anomaly_score": round(float(anomaly_score[0, 0]), 4),
            "risk_level": "HIGH" if prob >= 0.7 else "MEDIUM" if prob >= 0.4 else "LOW",
        })

    return results


def output_fn(prediction, accept="application/json"):
    return json.dumps(prediction), accept
