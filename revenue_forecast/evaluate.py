"""Evaluate forecast accuracy with backtesting."""

import json
import logging
import numpy as np
import pandas as pd

from revenue_forecast.data_prep import generate_revenue_data, split_train_test, compute_metrics

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def backtest_naive(series_dict: dict, prediction_length: int = 30) -> dict:
    """Backtest using naive forecast (last value repeated) as baseline."""
    train, test = split_train_test(series_dict, prediction_length)
    results = {}

    for name in series_dict:
        actual = test[name]["revenue"].values
        last_value = train[name]["revenue"].iloc[-1]
        predicted = np.full(prediction_length, last_value)
        metrics = compute_metrics(actual[:len(predicted)], predicted)
        results[name] = {"method": "naive", **metrics}

    return results


def backtest_seasonal_naive(series_dict: dict, prediction_length: int = 30, season: int = 7) -> dict:
    """Backtest using seasonal naive (same day last week)."""
    train, test = split_train_test(series_dict, prediction_length)
    results = {}

    for name in series_dict:
        actual = test[name]["revenue"].values
        last_season = train[name]["revenue"].iloc[-season:].values
        predicted = np.tile(last_season, (prediction_length // season) + 1)[:prediction_length]
        metrics = compute_metrics(actual[:len(predicted)], predicted)
        results[name] = {"method": "seasonal_naive", **metrics}

    return results


def backtest_moving_average(series_dict: dict, prediction_length: int = 30, window: int = 30) -> dict:
    """Backtest using moving average forecast."""
    train, test = split_train_test(series_dict, prediction_length)
    results = {}

    for name in series_dict:
        actual = test[name]["revenue"].values
        ma_value = train[name]["revenue"].iloc[-window:].mean()
        predicted = np.full(prediction_length, ma_value)
        metrics = compute_metrics(actual[:len(predicted)], predicted)
        results[name] = {"method": "moving_average", **metrics}

    return results


def run_full_evaluation(prediction_length: int = 30) -> dict:
    """Run all backtests and produce comparison report."""
    series = generate_revenue_data(n_series=5, n_days=730, seed=42)

    naive = backtest_naive(series, prediction_length)
    seasonal = backtest_seasonal_naive(series, prediction_length)
    ma = backtest_moving_average(series, prediction_length)

    report = {"prediction_length": prediction_length, "series": {}}

    for name in series:
        report["series"][name] = {
            "naive": naive[name],
            "seasonal_naive": seasonal[name],
            "moving_average": ma[name],
            "best_method": min(
                [("naive", naive[name]["mape_pct"]),
                 ("seasonal_naive", seasonal[name]["mape_pct"]),
                 ("moving_average", ma[name]["mape_pct"])],
                key=lambda x: x[1],
            )[0],
        }

    # Summary
    avg_mape = {
        "naive": np.mean([naive[n]["mape_pct"] for n in series]),
        "seasonal_naive": np.mean([seasonal[n]["mape_pct"] for n in series]),
        "moving_average": np.mean([ma[n]["mape_pct"] for n in series]),
    }
    report["summary"] = {
        "avg_mape_by_method": {k: round(v, 2) for k, v in avg_mape.items()},
        "best_baseline": min(avg_mape, key=avg_mape.get),
    }

    return report


if __name__ == "__main__":
    report = run_full_evaluation()
    print(json.dumps(report, indent=2))
