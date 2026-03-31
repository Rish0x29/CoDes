import pytest
import sys, os
import pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from data_lake.quality.checks import DataQualityChecker


@pytest.fixture
def sample_df():
    return pd.DataFrame({
        "id": range(100),
        "name": [f"item_{i}" for i in range(100)],
        "price": [10.0 + i * 0.5 for i in range(100)],
        "category": ["A"] * 50 + ["B"] * 50,
    })


def test_not_null_passes(sample_df):
    checker = DataQualityChecker()
    assert checker.expect_column_values_to_not_be_null(sample_df, "id") is True


def test_not_null_fails():
    df = pd.DataFrame({"x": [1, None, None, 4, None]})
    checker = DataQualityChecker()
    assert checker.expect_column_values_to_not_be_null(df, "x", threshold=0.95) is False


def test_unique_passes(sample_df):
    checker = DataQualityChecker()
    assert checker.expect_column_values_to_be_unique(sample_df, "id") is True


def test_between_passes(sample_df):
    checker = DataQualityChecker()
    assert checker.expect_column_values_to_be_between(sample_df, "price", 0, 1000) is True


def test_in_set(sample_df):
    checker = DataQualityChecker()
    assert checker.expect_column_values_to_be_in_set(sample_df, "category", {"A", "B"}) is True


def test_summary(sample_df):
    checker = DataQualityChecker()
    checker.expect_column_values_to_not_be_null(sample_df, "id")
    checker.expect_column_values_to_be_unique(sample_df, "id")
    summary = checker.summary()
    assert summary["total_checks"] == 2
    assert summary["all_passed"] is True
