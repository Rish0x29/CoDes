import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from churn_prediction.generate_data import generate_churn_data


def test_generate_has_required_cols():
    df = generate_churn_data(100)
    required = ["customer_id", "tenure", "contract", "monthly_charges", "churn"]
    for col in required:
        assert col in df.columns


def test_data_ranges():
    df = generate_churn_data(1000)
    assert df["tenure"].min() >= 1
    assert df["tenure"].max() <= 72
    assert df["monthly_charges"].min() >= 0
    assert df["satisfaction_score"].isin([1, 2, 3, 4, 5]).all()
