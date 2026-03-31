"""Market data tool - provides stock metrics and market info."""

import random
import logging

logger = logging.getLogger(__name__)

# Simulated market data (in production, this calls Alpha Vantage / Yahoo Finance API)
MARKET_DATA = {
    "AAPL": {"price": 178.50, "pe_ratio": 28.5, "market_cap": "2.8T", "dividend_yield": 0.55,
             "52w_high": 199.62, "52w_low": 143.90, "sector": "Technology", "beta": 1.25},
    "MSFT": {"price": 378.20, "pe_ratio": 35.2, "market_cap": "2.8T", "dividend_yield": 0.75,
             "52w_high": 384.30, "52w_low": 275.37, "sector": "Technology", "beta": 0.92},
    "GOOGL": {"price": 141.80, "pe_ratio": 24.8, "market_cap": "1.8T", "dividend_yield": 0.0,
              "52w_high": 153.78, "52w_low": 102.21, "sector": "Technology", "beta": 1.10},
    "AMZN": {"price": 155.30, "pe_ratio": 60.5, "market_cap": "1.6T", "dividend_yield": 0.0,
             "52w_high": 170.10, "52w_low": 101.26, "sector": "Consumer Discretionary", "beta": 1.18},
    "NVDA": {"price": 495.20, "pe_ratio": 65.3, "market_cap": "1.2T", "dividend_yield": 0.04,
             "52w_high": 505.48, "52w_low": 222.97, "sector": "Technology", "beta": 1.72},
    "JPM": {"price": 155.80, "pe_ratio": 10.2, "market_cap": "450B", "dividend_yield": 2.60,
            "52w_high": 172.96, "52w_low": 124.86, "sector": "Financials", "beta": 1.12},
    "SPY": {"price": 455.50, "pe_ratio": 22.1, "market_cap": "410B", "dividend_yield": 1.45,
            "52w_high": 479.98, "52w_low": 385.92, "sector": "Index", "beta": 1.00},
}


def get_market_data(ticker: str, metrics: list = None) -> dict:
    """Get market data for a ticker."""
    ticker = ticker.upper()
    data = MARKET_DATA.get(ticker)

    if not data:
        # Generate plausible data for unknown tickers
        data = {
            "price": round(random.uniform(20, 500), 2),
            "pe_ratio": round(random.uniform(8, 50), 1),
            "market_cap": f"{random.randint(1, 500)}B",
            "dividend_yield": round(random.uniform(0, 4), 2),
            "52w_high": 0, "52w_low": 0,
            "sector": "Unknown", "beta": round(random.uniform(0.5, 2.0), 2),
            "_note": "Simulated data - connect to real API for production use",
        }
        data["52w_high"] = round(data["price"] * random.uniform(1.05, 1.40), 2)
        data["52w_low"] = round(data["price"] * random.uniform(0.60, 0.95), 2)

    result = {"ticker": ticker}

    if metrics:
        for m in metrics:
            if m in data:
                result[m] = data[m]
    else:
        result.update(data)

    # Add computed fields
    if "price" in result and "52w_high" in data and "52w_low" in data:
        range_52w = data["52w_high"] - data["52w_low"]
        if range_52w > 0:
            result["position_in_52w_range_pct"] = round(
                (data["price"] - data["52w_low"]) / range_52w * 100, 1)

    return result
