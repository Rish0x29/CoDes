"""Data preparation for DeepAR time-series forecasting."""

import json
import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def generate_revenue_data(
    n_series: int = 5,
    n_days: int = 730,
    start_date: str = "2022-01-01",
    seed: int = 42,
) -> dict:
    """
    Generate synthetic revenue time-series data for multiple product lines.

    Returns dict with keys as series names and values as DataFrames.
    """
    rng = np.random.RandomState(seed)
    dates = pd.date_range(start=start_date, periods=n_days, freq="D")

    series_names = ["Product_A", "Product_B", "Product_C", "SaaS_Revenue", "Consulting"]
    base_revenues = [5000, 3000, 8000, 15000, 2000]
    growth_rates = [0.0003, 0.0005, 0.0002, 0.0008, 0.0001]

    all_series = {}

    for i in range(min(n_series, len(series_names))):
        name = series_names[i]
        base = base_revenues[i]
        growth = growth_rates[i]

        trend = base * np.exp(growth * np.arange(n_days))
        weekly_seasonal = base * 0.15 * np.sin(2 * np.pi * np.arange(n_days) / 7)
        monthly_seasonal = base * 0.10 * np.sin(2 * np.pi * np.arange(n_days) / 30.44)
        yearly_seasonal = base * 0.25 * np.sin(2 * np.pi * (np.arange(n_days) - 90) / 365.25)
        noise = rng.normal(0, base * 0.05, n_days)

        # Add occasional spikes (promotions, events)
        spikes = np.zeros(n_days)
        spike_days = rng.choice(n_days, size=n_days // 60, replace=False)
        spikes[spike_days] = rng.uniform(base * 0.3, base * 0.8, len(spike_days))

        revenue = trend + weekly_seasonal + monthly_seasonal + yearly_seasonal + noise + spikes
        revenue = np.maximum(revenue, base * 0.1)

        df = pd.DataFrame({"date": dates, "revenue": revenue.round(2)})
        df = df.set_index("date")
        all_series[name] = df

    return all_series


def to_deepar_format(series_dict: dict, prediction_length: int = 30) -> list:
    """Convert time-series data to DeepAR JSON Lines format."""
    records = []
    for name, df in series_dict.items():
        start = df.index[0].strftime("%Y-%m-%d %H:%M:%S")
        target = df["revenue"].tolist()

        records.append({
            "start": start,
            "target": target,
            "cat": [list(series_dict.keys()).index(name)],
            "dynamic_feat": [],
        })

    return records


def save_deepar_jsonlines(records: list, filepath: str):
    """Save records in JSON Lines format for DeepAR."""
    with open(filepath, "w") as f:
        for record in records:
            f.write(json.dumps(record) + "\n")
    logger.info(f"Saved {len(records)} series to {filepath}")


def split_train_test(series_dict: dict, prediction_length: int = 30) -> tuple:
    """Split data into training and test sets."""
    train_series = {}
    test_series = {}

    for name, df in series_dict.items():
        cutoff = len(df) - prediction_length
        train_series[name] = df.iloc[:cutoff]
        test_series[name] = df.iloc[cutoff:]

    return train_series, test_series


def compute_metrics(actual: np.ndarray, predicted: np.ndarray) -> dict:
    """Compute forecast accuracy metrics."""
    mae = np.mean(np.abs(actual - predicted))
    rmse = np.sqrt(np.mean((actual - predicted) ** 2))
    mape = np.mean(np.abs((actual - predicted) / np.maximum(actual, 1))) * 100
    smape = np.mean(2 * np.abs(actual - predicted) / (np.abs(actual) + np.abs(predicted) + 1e-8)) * 100

    return {
        "mae": round(float(mae), 2),
        "rmse": round(float(rmse), 2),
        "mape_pct": round(float(mape), 2),
        "smape_pct": round(float(smape), 2),
    }


if __name__ == "__main__":
    series = generate_revenue_data(n_series=5, n_days=730)
    for name, df in series.items():
        print(f"{name}: {len(df)} days, avg revenue: ${df['revenue'].mean():,.2f}")

    records = to_deepar_format(series)
    save_deepar_jsonlines(records, "train.jsonl")
    print(f"\nSaved {len(records)} series to train.jsonl")
