import pytest
import sys, os
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from fraud_detection.train import generate_fraud_data, prepare_features, FEATURE_COLS


def test_generate_fraud_data():
    df = generate_fraud_data(1000, fraud_rate=0.05)
    assert len(df) == 1000
    assert "is_fraud" in df.columns
    assert 0.03 <= df["is_fraud"].mean() <= 0.08


def test_generate_has_all_features():
    df = generate_fraud_data(100)
    for col in FEATURE_COLS:
        assert col in df.columns, f"Missing column: {col}"


def test_prepare_features():
    df = generate_fraud_data(500)
    X, y, le, scaler, names = prepare_features(df, fit=True)
    assert X.shape[0] == 500
    assert len(y) == 500
    assert X.shape[1] == len(FEATURE_COLS) + 1  # +1 for encoded category


def test_prepare_features_transform():
    df1 = generate_fraud_data(500, seed=1)
    X1, _, le, scaler, _ = prepare_features(df1, fit=True)
    df2 = generate_fraud_data(100, seed=2)
    X2, _, _, _, _ = prepare_features(df2, label_encoder=le, scaler=scaler, fit=False)
    assert X2.shape[1] == X1.shape[1]
