"""Tests for the backtesting engine."""

import numpy as np
import pandas as pd
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from trading_bot.backtest import run_backtest, BacktestResult
from trading_bot.data_fetcher import generate_sample_data


@pytest.fixture
def sample_data():
    return generate_sample_data(days=252, start_price=150.0, volatility=0.025, seed=42)


@pytest.fixture
def backtest_result(sample_data):
    return run_backtest(sample_data, initial_capital=100000.0, position_size_pct=0.02, stop_loss_pct=0.02)


class TestRunBacktest:
    def test_returns_backtest_result(self, sample_data):
        result = run_backtest(sample_data)
        assert isinstance(result, BacktestResult)

    def test_equity_curve_length(self, sample_data, backtest_result):
        assert len(backtest_result.equity_curve) == len(sample_data)

    def test_equity_starts_at_capital(self, backtest_result):
        assert backtest_result.equity_curve.iloc[0] == pytest.approx(100000.0, rel=0.01)

    def test_equity_never_negative(self, backtest_result):
        assert (backtest_result.equity_curve > 0).all()

    def test_trades_alternate_buy_sell(self, backtest_result):
        trades = backtest_result.trades
        if len(trades) >= 2:
            for i in range(1, len(trades)):
                if trades[i-1]["type"] == "BUY":
                    assert trades[i]["type"] == "SELL"


class TestBacktestResult:
    def test_total_return(self, backtest_result):
        total_ret = backtest_result.total_return
        assert isinstance(total_ret, float)

    def test_win_rate_range(self, backtest_result):
        assert 0.0 <= backtest_result.win_rate <= 1.0

    def test_max_drawdown_negative(self, backtest_result):
        assert backtest_result.max_drawdown <= 0.0

    def test_sharpe_ratio(self, backtest_result):
        sr = backtest_result.sharpe_ratio
        assert isinstance(sr, float)

    def test_sortino_ratio(self, backtest_result):
        sr = backtest_result.sortino_ratio
        assert isinstance(sr, float)

    def test_profit_factor(self, backtest_result):
        pf = backtest_result.profit_factor
        assert pf >= 0.0

    def test_summary_keys(self, backtest_result):
        summary = backtest_result.summary()
        expected_keys = ["initial_capital", "final_equity", "total_return_pct", "total_trades",
                         "winning_trades", "losing_trades", "win_rate_pct", "max_drawdown_pct",
                         "sharpe_ratio", "sortino_ratio", "profit_factor", "avg_trade_pnl",
                         "max_consecutive_losses"]
        for key in expected_keys:
            assert key in summary

    def test_print_report(self, backtest_result, capsys):
        backtest_result.print_report()
        captured = capsys.readouterr()
        assert "BACKTEST PERFORMANCE REPORT" in captured.out
        assert "Total Return" in captured.out


class TestEdgeCases:
    def test_no_signals_short_data(self):
        df = generate_sample_data(days=30, start_price=100.0)
        result = run_backtest(df)
        assert result.total_trades == 0

    def test_high_volatility(self):
        df = generate_sample_data(days=252, volatility=0.08, seed=123)
        result = run_backtest(df)
        assert isinstance(result, BacktestResult)

    def test_with_commission(self, sample_data):
        result = run_backtest(sample_data, commission_per_share=0.01)
        assert isinstance(result, BacktestResult)
