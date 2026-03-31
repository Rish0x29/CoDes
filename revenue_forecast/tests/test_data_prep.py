import pytest
import sys, os
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from revenue_forecast.data_prep import (
    generate_revenue_data, to_deepar_format, split_train_test, compute_metrics,
)


def test_generate_revenue_data():
    series = generate_revenue_data(n_series=3, n_days=365)
    assert len(series) == 3
    for name, df in series.items():
        assert len(df) == 365
        assert "revenue" in df.columns
        assert (df["revenue"] > 0).all()


def test_to_deepar_format():
    series = generate_revenue_data(n_series=2, n_days=100)
    records = to_deepar_format(series)
    assert len(records) == 2
    for rec in records:
        assert "start" in rec
        assert "target" in rec
        assert len(rec["target"]) == 100


def test_split_train_test():
    series = generate_revenue_data(n_series=2, n_days=100)
    train, test = split_train_test(series, prediction_length=30)
    for name in series:
        assert len(train[name]) == 70
        assert len(test[name]) == 30


def test_compute_metrics():
    actual = np.array([100, 200, 300, 400, 500])
    predicted = np.array([110, 190, 310, 390, 510])
    metrics = compute_metrics(actual, predicted)
    assert metrics["mae"] > 0
    assert metrics["rmse"] > 0
    assert metrics["mape_pct"] > 0
