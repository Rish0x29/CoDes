import pytest
import sys, os
import numpy as np
import pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from credit_risk.preprocessing import add_derived_features, build_preprocessor, preprocess_data
from credit_risk.generate_sample_data import generate_credit_data


@pytest.fixture
def sample_data():
    return generate_credit_data(200, seed=42)


def test_derived_features(sample_data):
    result = add_derived_features(sample_data)
    assert "debt_to_income_ratio" in result.columns
    assert "loan_to_income_ratio" in result.columns
    assert "monthly_payment_estimate" in result.columns
    assert "risk_score_composite" in result.columns
    assert not result["monthly_payment_estimate"].isna().any()


def test_preprocessor_fit_transform(sample_data):
    X, y, preprocessor, feature_names = preprocess_data(sample_data, fit=True)
    assert X.shape[0] == len(sample_data)
    assert X.shape[1] > 0
    assert len(y) == len(sample_data)
    assert len(feature_names) == X.shape[1]


def test_preprocessor_transform(sample_data):
    X, y, preprocessor, _ = preprocess_data(sample_data, fit=True)
    new_data = generate_credit_data(50, seed=99)
    X2, y2, _, _ = preprocess_data(new_data, preprocessor=preprocessor, fit=False)
    assert X2.shape[1] == X.shape[1]


def test_generate_credit_data():
    df = generate_credit_data(1000)
    assert len(df) == 1000
    assert "default" in df.columns
    assert df["default"].isin([0, 1]).all()
    assert 0.05 < df["default"].mean() < 0.5
