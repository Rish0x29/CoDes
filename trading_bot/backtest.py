"""
Backtesting Engine - Historical Strategy Testing with Performance Metrics.
"""

import numpy as np
import pandas as pd
from typing import Optional
from trading_bot.strategy import Signal, generate_signals_for_dataframe


class BacktestResult:
    def __init__(self, trades: list, equity_curve: pd.Series, initial_capital: float):
        self.trades = trades
        self.equity_curve = equity_curve
        self.initial_capital = initial_capital

    @property
    def total_return(self) -> float:
        if len(self.equity_curve) == 0:
            return 0.0
        return (self.equity_curve.iloc[-1] - self.initial_capital) / self.initial_capital

    @property
    def total_trades(self) -> int:
        return len([t for t in self.trades if t["type"] == "SELL"])

    @property
    def winning_trades(self) -> int:
        return len([t for t in self.trades if t["type"] == "SELL" and t.get("pnl", 0) > 0])

    @property
    def losing_trades(self) -> int:
        return len([t for t in self.trades if t["type"] == "SELL" and t.get("pnl", 0) <= 0])

    @property
    def win_rate(self) -> float:
        if self.total_trades == 0:
            return 0.0
        return self.winning_trades / self.total_trades

    @property
    def max_drawdown(self) -> float:
        if len(self.equity_curve) == 0:
            return 0.0
        peak = self.equity_curve.expanding(min_periods=1).max()
        drawdown = (self.equity_curve - peak) / peak
        return drawdown.min()

    @property
    def sharpe_ratio(self) -> float:
        if len(self.equity_curve) < 2:
            return 0.0
        returns = self.equity_curve.pct_change().dropna()
        if returns.std() == 0:
            return 0.0
        return np.sqrt(252) * returns.mean() / returns.std()

    @property
    def sortino_ratio(self) -> float:
        if len(self.equity_curve) < 2:
            return 0.0
        returns = self.equity_curve.pct_change().dropna()
        downside = returns[returns < 0]
        if len(downside) == 0 or downside.std() == 0:
            return 0.0
        return np.sqrt(252) * returns.mean() / downside.std()

    @property
    def profit_factor(self) -> float:
        gross_profit = sum(t.get("pnl", 0) for t in self.trades if t["type"] == "SELL" and t.get("pnl", 0) > 0)
        gross_loss = abs(sum(t.get("pnl", 0) for t in self.trades if t["type"] == "SELL" and t.get("pnl", 0) < 0))
        if gross_loss == 0:
            return float("inf") if gross_profit > 0 else 0.0
        return gross_profit / gross_loss

    @property
    def avg_trade_pnl(self) -> float:
        sell_trades = [t for t in self.trades if t["type"] == "SELL"]
        if not sell_trades:
            return 0.0
        return np.mean([t.get("pnl", 0) for t in sell_trades])

    @property
    def max_consecutive_losses(self) -> int:
        max_losses = 0
        current_losses = 0
        for t in self.trades:
            if t["type"] == "SELL":
                if t.get("pnl", 0) <= 0:
                    current_losses += 1
                    max_losses = max(max_losses, current_losses)
                else:
                    current_losses = 0
        return max_losses

    def summary(self) -> dict:
        return {
            "initial_capital": self.initial_capital,
            "final_equity": round(self.equity_curve.iloc[-1], 2) if len(self.equity_curve) > 0 else self.initial_capital,
            "total_return_pct": round(self.total_return * 100, 2),
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate_pct": round(self.win_rate * 100, 2),
            "max_drawdown_pct": round(self.max_drawdown * 100, 2),
            "sharpe_ratio": round(self.sharpe_ratio, 3),
            "sortino_ratio": round(self.sortino_ratio, 3),
            "profit_factor": round(self.profit_factor, 3),
            "avg_trade_pnl": round(self.avg_trade_pnl, 2),
            "max_consecutive_losses": self.max_consecutive_losses,
        }

    def print_report(self):
        s = self.summary()
        print("\n" + "=" * 60)
        print("          BACKTEST PERFORMANCE REPORT")
        print("=" * 60)
        print(f"  Initial Capital:       ${s['initial_capital']:,.2f}")
        print(f"  Final Equity:          ${s['final_equity']:,.2f}")
        print(f"  Total Return:          {s['total_return_pct']:+.2f}%")
        print(f"  Max Drawdown:          {s['max_drawdown_pct']:.2f}%")
        print("-" * 60)
        print(f"  Total Trades:          {s['total_trades']}")
        print(f"  Win Rate:              {s['win_rate_pct']:.1f}%")
        print(f"  Profit Factor:         {s['profit_factor']:.3f}")
        print(f"  Avg Trade P&L:         ${s['avg_trade_pnl']:,.2f}")
        print(f"  Max Consecutive Losses: {s['max_consecutive_losses']}")
        print("-" * 60)
        print(f"  Sharpe Ratio:          {s['sharpe_ratio']:.3f}")
        print(f"  Sortino Ratio:         {s['sortino_ratio']:.3f}")
        print("=" * 60)


def run_backtest(
    df: pd.DataFrame,
    initial_capital: float = 100000.0,
    position_size_pct: float = 0.02,
    stop_loss_pct: float = 0.02,
    sma_short_period: int = 20,
    sma_long_period: int = 50,
    rsi_period: int = 14,
    rsi_entry_max: float = 70.0,
    rsi_overbought: float = 80.0,
    commission_per_share: float = 0.0,
) -> BacktestResult:
    """
    Run a full backtest on historical OHLCV data.

    Parameters
    ----------
    df : pd.DataFrame
        OHLCV data with columns: open, high, low, close, volume.
    initial_capital : float
        Starting capital.
    position_size_pct : float
        Fraction of equity to risk per trade.
    stop_loss_pct : float
        Stop-loss percentage.
    sma_short_period, sma_long_period, rsi_period : int
        Strategy parameters.
    rsi_entry_max, rsi_overbought : float
        RSI thresholds.
    commission_per_share : float
        Trading commission per share.

    Returns
    -------
    BacktestResult
        Backtest results with trades, equity curve, and metrics.
    """
    signals_df = generate_signals_for_dataframe(
        df, sma_short_period, sma_long_period, rsi_period, rsi_entry_max, rsi_overbought
    )

    cash = initial_capital
    shares = 0
    entry_price = 0.0
    trades = []
    equity_values = []
    equity_dates = []

    for i in range(len(signals_df)):
        row = signals_df.iloc[i]
        price = row["close"]
        signal = row["signal"]

        # Check stop-loss
        if shares > 0 and entry_price > 0:
            pnl_pct = (price - entry_price) / entry_price
            if pnl_pct <= -stop_loss_pct:
                signal = Signal.SELL.value

        if signal == Signal.BUY.value and shares == 0:
            equity = cash
            risk_amount = equity * position_size_pct
            buy_shares = int(risk_amount / price)
            if buy_shares > 0:
                commission = buy_shares * commission_per_share
                cost = buy_shares * price + commission
                if cost <= cash:
                    shares = buy_shares
                    entry_price = price
                    cash -= cost
                    trades.append({
                        "date": signals_df.index[i],
                        "type": "BUY",
                        "price": price,
                        "shares": shares,
                        "commission": commission,
                        "reason": row.get("reason", ""),
                    })

        elif signal == Signal.SELL.value and shares > 0:
            commission = shares * commission_per_share
            revenue = shares * price - commission
            pnl = (price - entry_price) * shares - commission * 2
            cash += revenue
            trades.append({
                "date": signals_df.index[i],
                "type": "SELL",
                "price": price,
                "shares": shares,
                "commission": commission,
                "pnl": round(pnl, 2),
                "pnl_pct": round((price - entry_price) / entry_price * 100, 2),
                "reason": row.get("reason", ""),
            })
            shares = 0
            entry_price = 0.0

        equity = cash + shares * price
        equity_values.append(equity)
        equity_dates.append(signals_df.index[i])

    equity_curve = pd.Series(equity_values, index=equity_dates)
    return BacktestResult(trades, equity_curve, initial_capital)


if __name__ == "__main__":
    from trading_bot.data_fetcher import generate_sample_data

    print("Running backtest with sample data...")
    df = generate_sample_data(days=252, start_price=150.0, volatility=0.025, seed=42)
    result = run_backtest(df, initial_capital=100000, position_size_pct=0.02, stop_loss_pct=0.02)
    result.print_report()

    print("\nTrade Log:")
    for t in result.trades:
        pnl_str = f"  P&L: ${t['pnl']:+.2f} ({t['pnl_pct']:+.1f}%)" if "pnl" in t else ""
        print(f"  {t['date'].strftime('%Y-%m-%d')} {t['type']:4s} {t['shares']:4d} @ ${t['price']:.2f}{pnl_str}")
