import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from financial_chatbot.tools.portfolio import analyze_portfolio
from financial_chatbot.tools.market_data import get_market_data
from financial_chatbot.tools.risk import calculate_risk


class TestPortfolioAnalysis:
    def test_basic_analysis(self):
        result = analyze_portfolio([
            {"ticker": "AAPL", "allocation_pct": 40},
            {"ticker": "MSFT", "allocation_pct": 30},
            {"ticker": "BND", "allocation_pct": 30},
        ])
        assert result["num_holdings"] == 3
        assert result["total_allocation_pct"] == 100
        assert "diversification_score" in result
        assert 0 <= result["diversification_score"] <= 100

    def test_concentrated_portfolio_warning(self):
        result = analyze_portfolio([
            {"ticker": "AAPL", "allocation_pct": 80},
            {"ticker": "MSFT", "allocation_pct": 20},
        ])
        assert len(result["warnings"]) > 0

    def test_risk_tolerance(self):
        result = analyze_portfolio(
            [{"ticker": "AAPL", "allocation_pct": 90}, {"ticker": "MSFT", "allocation_pct": 10}],
            risk_tolerance="conservative",
        )
        assert any("stock" in r.lower() or "bond" in r.lower() for r in result["recommendations"])


class TestMarketData:
    def test_known_ticker(self):
        result = get_market_data("AAPL")
        assert result["ticker"] == "AAPL"
        assert "price" in result
        assert result["price"] > 0

    def test_specific_metrics(self):
        result = get_market_data("MSFT", metrics=["price", "pe_ratio"])
        assert "price" in result
        assert "pe_ratio" in result

    def test_unknown_ticker(self):
        result = get_market_data("XYZ123")
        assert result["ticker"] == "XYZ123"
        assert "price" in result


class TestRiskCalculation:
    def test_basic_risk(self):
        result = calculate_risk(100000, [
            {"ticker": "AAPL", "allocation_pct": 50},
            {"ticker": "BND", "allocation_pct": 50},
        ])
        assert "annualized_volatility_pct" in result
        assert "value_at_risk" in result
        assert "risk_rating" in result

    def test_high_risk_portfolio(self):
        result = calculate_risk(50000, [
            {"ticker": "NVDA", "allocation_pct": 50},
            {"ticker": "TSLA", "allocation_pct": 50},
        ])
        assert result["risk_rating"] in ["HIGH", "VERY HIGH"]

    def test_low_risk_portfolio(self):
        result = calculate_risk(100000, [
            {"ticker": "BND", "allocation_pct": 60},
            {"ticker": "AGG", "allocation_pct": 40},
        ])
        assert result["risk_rating"] == "LOW"
