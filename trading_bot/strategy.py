"""
Trading Strategy Module - SMA Crossover + RSI Filter.

Implements a moving average crossover strategy with RSI confirmation.
Entry: SMA-20 crosses above SMA-50 AND RSI(14) < 70
Exit:  SMA-20 crosses below SMA-50 OR RSI(14) > 80 OR stop-loss at -2%
"""

import numpy as np
import pandas as pd
from enum import Enum


class Signal(Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


def compute_sma(prices: pd.Series, period: int) -> pd.Series:
    if len(prices) < period:
        return pd.Series(np.nan, index=prices.index)
    return prices.rolling(window=period, min_periods=period).mean()


def compute_ema(prices: pd.Series, period: int) -> pd.Series:
    return prices.ewm(span=period, adjust=False).mean()


def compute_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    delta = prices.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi


def compute_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return true_range.rolling(window=period, min_periods=period).mean()


def compute_bollinger_bands(prices: pd.Series, period: int = 20, std_dev: float = 2.0):
    sma = compute_sma(prices, period)
    rolling_std = prices.rolling(window=period, min_periods=period).std()
    upper = sma + (rolling_std * std_dev)
    lower = sma - (rolling_std * std_dev)
    return upper, sma, lower


def generate_signal(
    df: pd.DataFrame,
    sma_short_period: int = 20,
    sma_long_period: int = 50,
    rsi_period: int = 14,
    rsi_entry_max: float = 70.0,
    rsi_overbought: float = 80.0,
    stop_loss_pct: float = 0.02,
    current_position: dict = None,
) -> dict:
    if len(df) < sma_long_period + 2:
        return {
            "signal": Signal.HOLD,
            "reason": f"Insufficient data: need {sma_long_period + 2} bars, have {len(df)}",
            "indicators": {},
        }

    close = df["close"]
    sma_short = compute_sma(close, sma_short_period)
    sma_long = compute_sma(close, sma_long_period)
    rsi = compute_rsi(close, rsi_period)
    atr = compute_atr(df["high"], df["low"], close, rsi_period)

    current_close = close.iloc[-1]
    current_sma_short = sma_short.iloc[-1]
    current_sma_long = sma_long.iloc[-1]
    prev_sma_short = sma_short.iloc[-2]
    prev_sma_long = sma_long.iloc[-2]
    current_rsi = rsi.iloc[-1]
    current_atr = atr.iloc[-1]

    indicators = {
        "sma_short": round(float(current_sma_short), 4),
        "sma_long": round(float(current_sma_long), 4),
        "rsi": round(float(current_rsi), 2),
        "close": round(float(current_close), 4),
        "atr": round(float(current_atr), 4) if not np.isnan(current_atr) else None,
    }

    if current_position and current_position.get("entry_price"):
        entry_price = current_position["entry_price"]
        pnl_pct = (current_close - entry_price) / entry_price
        if pnl_pct <= -stop_loss_pct:
            return {
                "signal": Signal.SELL,
                "reason": f"Stop-loss triggered: PnL {pnl_pct:.2%} <= -{stop_loss_pct:.2%}",
                "indicators": indicators,
            }

    if current_position and current_rsi > rsi_overbought:
        return {
            "signal": Signal.SELL,
            "reason": f"RSI overbought: {current_rsi:.1f} > {rsi_overbought}",
            "indicators": indicators,
        }

    bullish_cross = prev_sma_short <= prev_sma_long and current_sma_short > current_sma_long
    bearish_cross = prev_sma_short >= prev_sma_long and current_sma_short < current_sma_long

    if bullish_cross and current_rsi < rsi_entry_max and not current_position:
        return {
            "signal": Signal.BUY,
            "reason": f"Bullish SMA crossover (SMA{sma_short_period} crossed above SMA{sma_long_period}) with RSI={current_rsi:.1f}",
            "indicators": indicators,
        }

    if bearish_cross and current_position:
        return {
            "signal": Signal.SELL,
            "reason": f"Bearish SMA crossover (SMA{sma_short_period} crossed below SMA{sma_long_period})",
            "indicators": indicators,
        }

    return {
        "signal": Signal.HOLD,
        "reason": "No signal conditions met",
        "indicators": indicators,
    }


def generate_signals_for_dataframe(
    df: pd.DataFrame,
    sma_short_period: int = 20,
    sma_long_period: int = 50,
    rsi_period: int = 14,
    rsi_entry_max: float = 70.0,
    rsi_overbought: float = 80.0,
) -> pd.DataFrame:
    result = df.copy()
    result["sma_short"] = compute_sma(result["close"], sma_short_period)
    result["sma_long"] = compute_sma(result["close"], sma_long_period)
    result["rsi"] = compute_rsi(result["close"], rsi_period)
    result["signal"] = Signal.HOLD.value
    result["reason"] = ""

    for i in range(sma_long_period + 1, len(result)):
        prev_short = result["sma_short"].iloc[i - 1]
        prev_long = result["sma_long"].iloc[i - 1]
        curr_short = result["sma_short"].iloc[i]
        curr_long = result["sma_long"].iloc[i]
        curr_rsi = result["rsi"].iloc[i]

        bullish_cross = prev_short <= prev_long and curr_short > curr_long
        bearish_cross = prev_short >= prev_long and curr_short < curr_long

        if bullish_cross and curr_rsi < rsi_entry_max:
            result.iloc[i, result.columns.get_loc("signal")] = Signal.BUY.value
            result.iloc[i, result.columns.get_loc("reason")] = "Bullish crossover"
        elif bearish_cross:
            result.iloc[i, result.columns.get_loc("signal")] = Signal.SELL.value
            result.iloc[i, result.columns.get_loc("reason")] = "Bearish crossover"
        elif curr_rsi > rsi_overbought:
            result.iloc[i, result.columns.get_loc("signal")] = Signal.SELL.value
            result.iloc[i, result.columns.get_loc("reason")] = "RSI overbought"

    return result
