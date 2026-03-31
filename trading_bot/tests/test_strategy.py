"""Tests for the trading strategy module."""

import numpy as np
import pandas as pd
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from trading_bot.strategy import (
    Signal, compute_sma, compute_rsi, compute_ema, compute_atr,
    compute_bollinger_bands, generate_signal, generate_signals_for_dataframe,
)
from trading_bot.data_fetcher import generate_sample_data


@pytest.fixture
def sample_prices():
    np.random.seed(42)
    dates = pd.bdate_range("2024-01-01", periods=100)
    prices = 100 + np.cumsum(np.random.randn(100) * 0.5)
    return pd.Series(prices, index=dates)


@pytest.fixture
def sample_ohlcv():
    return generate_sample_data(days=120, start_price=150.0, seed=42)


class TestComputeSMA:
    def test_basic_sma(self, sample_prices):
        sma = compute_sma(sample_prices, 10)
        assert len(sma) == len(sample_prices)
        assert sma.iloc[:9].isna().all()
        assert not sma.iloc[9:].isna().any()

    def test_sma_value(self):
        prices = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        sma = compute_sma(prices, 3)
        assert sma.iloc[2] == pytest.approx(2.0)
        assert sma.iloc[3] == pytest.approx(3.0)
        assert sma.iloc[4] == pytest.approx(4.0)

    def test_insufficient_data(self):
        prices = pd.Series([1.0, 2.0])
        sma = compute_sma(prices, 5)
        assert sma.isna().all()


class TestComputeRSI:
    def test_rsi_range(self, sample_prices):
        rsi = compute_rsi(sample_prices, 14)
        valid_rsi = rsi.dropna()
        assert (valid_rsi >= 0).all()
        assert (valid_rsi <= 100).all()

    def test_rsi_uptrend(self):
        prices = pd.Series(range(1, 30), dtype=float)
        rsi = compute_rsi(prices, 14)
        assert rsi.iloc[-1] > 70

    def test_rsi_downtrend(self):
        prices = pd.Series(list(range(30, 0, -1)), dtype=float)
        rsi = compute_rsi(prices, 14)
        assert rsi.iloc[-1] < 30


class TestComputeEMA:
    def test_ema_follows_price(self, sample_prices):
        ema = compute_ema(sample_prices, 10)
        assert len(ema) == len(sample_prices)
        assert not ema.isna().any()


class TestComputeATR:
    def test_atr_positive(self, sample_ohlcv):
        atr = compute_atr(sample_ohlcv["high"], sample_ohlcv["low"], sample_ohlcv["close"], 14)
        valid_atr = atr.dropna()
        assert (valid_atr > 0).all()


class TestComputeBollingerBands:
    def test_bands_order(self, sample_prices):
        upper, middle, lower = compute_bollinger_bands(sample_prices, 20)
        valid = ~upper.isna()
        assert (upper[valid] >= middle[valid]).all()
        assert (middle[valid] >= lower[valid]).all()


class TestGenerateSignal:
    def test_hold_insufficient_data(self):
        df = pd.DataFrame({"open": [1]*10, "high": [2]*10, "low": [0.5]*10,
                           "close": [1.5]*10, "volume": [100]*10})
        result = generate_signal(df, sma_long_period=50)
        assert result["signal"] == Signal.HOLD
        assert "Insufficient" in result["reason"]

    def test_signal_with_sample_data(self, sample_ohlcv):
        result = generate_signal(sample_ohlcv)
        assert result["signal"] in [Signal.BUY, Signal.SELL, Signal.HOLD]
        assert "indicators" in result
        assert "close" in result["indicators"]

    def test_stop_loss_triggered(self, sample_ohlcv):
        result = generate_signal(
            sample_ohlcv, stop_loss_pct=0.001,
            current_position={"entry_price": sample_ohlcv["close"].iloc[-1] * 1.1, "shares": 10}
        )
        if result["signal"] == Signal.SELL:
            assert "Stop-loss" in result["reason"] or "RSI" in result["reason"]

    def test_rsi_overbought_exit(self, sample_ohlcv):
        result = generate_signal(
            sample_ohlcv, rsi_overbought=1.0,
            current_position={"entry_price": 100.0, "shares": 10}
        )
        if result["signal"] == Signal.SELL:
            assert "RSI" in result["reason"] or "crossover" in result["reason"]


class TestGenerateSignalsForDataframe:
    def test_signals_columns(self, sample_ohlcv):
        result = generate_signals_for_dataframe(sample_ohlcv)
        assert "sma_short" in result.columns
        assert "sma_long" in result.columns
        assert "rsi" in result.columns
        assert "signal" in result.columns

    def test_signals_values(self, sample_ohlcv):
        result = generate_signals_for_dataframe(sample_ohlcv)
        valid_signals = set(result["signal"].unique())
        assert valid_signals.issubset({"BUY", "SELL", "HOLD"})
