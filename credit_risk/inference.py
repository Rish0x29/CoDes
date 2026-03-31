"""SageMaker inference handler for credit risk scoring."""

import os
import json
import logging
import numpy as np
import pandas as pd
import joblib

logger = logging.getLogger(__name__)

model = None
preprocessor = None


def model_fn(model_dir: str):
    """Load model and preprocessor from the model directory."""
    global model, preprocessor
    model = joblib.load(os.path.join(model_dir, "model.joblib"))
    preprocessor = joblib.load(os.path.join(model_dir, "preprocessor.joblib"))
    logger.info("Model and preprocessor loaded successfully")
    return model


def input_fn(request_body: str, request_content_type: str = "application/json"):
    """Parse input data."""
    if request_content_type == "application/json":
        data = json.loads(request_body)
        if isinstance(data, dict):
            data = [data]
        return pd.DataFrame(data)
    raise ValueError(f"Unsupported content type: {request_content_type}")


def predict_fn(input_data: pd.DataFrame, model_obj):
    """Generate predictions."""
    global preprocessor
    from credit_risk.preprocessing import add_derived_features

    df = add_derived_features(input_data)
    X = preprocessor.transform(df)

    probabilities = model_obj.predict_proba(X)[:, 1]
    predictions = model_obj.predict(X)

    results = []
    for i in range(len(predictions)):
        prob = float(probabilities[i])
        if prob < 0.3:
            risk_category = "LOW"
        elif prob < 0.6:
            risk_category = "MEDIUM"
        else:
            risk_category = "HIGH"

        results.append({
            "default_probability": round(prob, 4),
            "risk_category": risk_category,
            "prediction": int(predictions[i]),
            "risk_score": round(prob * 1000, 0),
        })

    return results


def output_fn(prediction, accept="application/json"):
    """Format output."""
    if accept == "application/json":
        return json.dumps({"predictions": prediction}), accept
    raise ValueError(f"Unsupported accept type: {accept}")
