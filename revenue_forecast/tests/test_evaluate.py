import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from revenue_forecast.evaluate import (
    backtest_naive, backtest_seasonal_naive, backtest_moving_average, run_full_evaluation,
)
from revenue_forecast.data_prep import generate_revenue_data


@pytest.fixture
def sample_series():
    return generate_revenue_data(n_series=2, n_days=200)


def test_backtest_naive(sample_series):
    results = backtest_naive(sample_series)
    for name, metrics in results.items():
        assert metrics["method"] == "naive"
        assert metrics["mape_pct"] > 0


def test_backtest_seasonal(sample_series):
    results = backtest_seasonal_naive(sample_series)
    for name, metrics in results.items():
        assert metrics["method"] == "seasonal_naive"


def test_backtest_ma(sample_series):
    results = backtest_moving_average(sample_series)
    for name, metrics in results.items():
        assert metrics["method"] == "moving_average"


def test_full_evaluation():
    report = run_full_evaluation(prediction_length=14)
    assert "summary" in report
    assert "series" in report
    assert report["summary"]["best_baseline"] in ["naive", "seasonal_naive", "moving_average"]
