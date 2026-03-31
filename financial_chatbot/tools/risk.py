"""Risk calculation tool for portfolio risk assessment."""

import math
import logging

logger = logging.getLogger(__name__)

# Historical volatility estimates (annualized)
VOLATILITY_MAP = {
    "AAPL": 0.28, "MSFT": 0.24, "GOOGL": 0.30, "AMZN": 0.32, "NVDA": 0.55,
    "META": 0.40, "TSLA": 0.60, "JPM": 0.25, "V": 0.22, "JNJ": 0.16,
    "SPY": 0.18, "QQQ": 0.25, "BND": 0.06, "AGG": 0.05, "TLT": 0.15,
    "GLD": 0.16, "XOM": 0.28, "PG": 0.18, "KO": 0.17, "DEFAULT": 0.30,
}


def calculate_risk(portfolio_value: float, holdings: list, time_horizon_years: float = 1.0) -> dict:
    """Calculate portfolio risk metrics."""
    total_alloc = sum(h.get("allocation_pct", 0) for h in holdings)
    if total_alloc == 0:
        return {"error": "No holdings provided"}

    # Weighted portfolio volatility (simplified - assumes zero correlation)
    weighted_vol_sq = 0
    individual_risks = []
    for h in holdings:
        ticker = h.get("ticker", "").upper()
        pct = h.get("allocation_pct", 0) / 100
        vol = VOLATILITY_MAP.get(ticker, VOLATILITY_MAP["DEFAULT"])
        weighted_vol_sq += (pct * vol) ** 2
        individual_risks.append({
            "ticker": ticker,
            "allocation_pct": h.get("allocation_pct", 0),
            "annualized_volatility": round(vol * 100, 1),
            "contribution_to_risk_pct": round((pct * vol) ** 2 / max(weighted_vol_sq, 0.0001) * 100, 1),
        })

    portfolio_vol = math.sqrt(weighted_vol_sq)
    annualized_vol = portfolio_vol

    # Value at Risk (parametric, 95% confidence)
    z_95 = 1.645
    z_99 = 2.326
    var_95_1d = portfolio_value * annualized_vol * z_95 / math.sqrt(252)
    var_99_1d = portfolio_value * annualized_vol * z_99 / math.sqrt(252)
    var_95_annual = portfolio_value * annualized_vol * z_95

    # Max drawdown estimate
    expected_max_dd = -annualized_vol * math.sqrt(time_horizon_years) * 2

    # Sharpe ratio estimate (assuming risk-free rate ~5%)
    risk_free_rate = 0.05
    expected_return = 0.10  # market average assumption
    sharpe_estimate = (expected_return - risk_free_rate) / max(annualized_vol, 0.01)

    # Risk rating
    if annualized_vol < 0.12:
        risk_rating = "LOW"
    elif annualized_vol < 0.25:
        risk_rating = "MODERATE"
    elif annualized_vol < 0.40:
        risk_rating = "HIGH"
    else:
        risk_rating = "VERY HIGH"

    # Recalculate contributions now that we have final vol
    for r in individual_risks:
        ticker = r["ticker"]
        pct = r["allocation_pct"] / 100
        vol = VOLATILITY_MAP.get(ticker, VOLATILITY_MAP["DEFAULT"])
        r["contribution_to_risk_pct"] = round((pct * vol) ** 2 / max(weighted_vol_sq, 0.0001) * 100, 1)

    return {
        "portfolio_value": portfolio_value,
        "annualized_volatility_pct": round(annualized_vol * 100, 2),
        "risk_rating": risk_rating,
        "value_at_risk": {
            "var_95_1day": round(var_95_1d, 2),
            "var_99_1day": round(var_99_1d, 2),
            "var_95_annual": round(var_95_annual, 2),
            "interpretation": f"95% confident daily loss won't exceed ${var_95_1d:,.2f}",
        },
        "expected_max_drawdown_pct": round(expected_max_dd * 100, 1),
        "estimated_sharpe_ratio": round(sharpe_estimate, 2),
        "time_horizon_years": time_horizon_years,
        "individual_risks": sorted(individual_risks, key=lambda x: x.get("annualized_volatility", 0), reverse=True),
        "recommendations": _risk_recommendations(annualized_vol, holdings),
    }


def _risk_recommendations(vol: float, holdings: list) -> list:
    recs = []
    if vol > 0.35:
        recs.append("Consider adding bonds (BND/AGG) to reduce overall volatility")
        recs.append("High-volatility holdings may benefit from stop-loss orders")
    if vol > 0.25:
        recs.append("Portfolio volatility is above average - ensure this matches your risk tolerance")
    if len(holdings) < 5:
        recs.append("Add more holdings for better diversification")
    high_vol_count = sum(1 for h in holdings if VOLATILITY_MAP.get(h.get("ticker", "").upper(), 0.30) > 0.40)
    if high_vol_count > 2:
        recs.append(f"You have {high_vol_count} highly volatile holdings - consider trimming positions")
    return recs
