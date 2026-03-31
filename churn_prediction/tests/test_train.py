import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from churn_prediction.generate_data import generate_churn_data
from churn_prediction.train import prepare_features


def test_generate_data():
    df = generate_churn_data(500)
    assert len(df) == 500
    assert "churn" in df.columns
    assert 0.1 < df["churn"].mean() < 0.6


def test_prepare_features():
    df = generate_churn_data(200)
    X, y, encoders, scaler = prepare_features(df, fit=True)
    assert X.shape[0] == 200
    assert len(y) == 200
    assert len(encoders) > 0


def test_prepare_features_transform():
    df1 = generate_churn_data(200, seed=1)
    X1, _, encoders, scaler = prepare_features(df1, fit=True)

    df2 = generate_churn_data(50, seed=2)
    X2, _, _, _ = prepare_features(df2, label_encoders=encoders, scaler=scaler, fit=False)
    assert X2.shape[1] == X1.shape[1]
