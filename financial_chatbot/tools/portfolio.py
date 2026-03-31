"""Portfolio analysis tool for the financial chatbot."""

import logging

logger = logging.getLogger(__name__)

SECTOR_MAP = {
    "AAPL": "Technology", "MSFT": "Technology", "GOOGL": "Technology",
    "AMZN": "Consumer Discretionary", "NVDA": "Technology", "META": "Technology",
    "TSLA": "Consumer Discretionary", "JPM": "Financials", "V": "Financials",
    "JNJ": "Healthcare", "UNH": "Healthcare", "PG": "Consumer Staples",
    "XOM": "Energy", "CVX": "Energy", "BRK.B": "Financials",
    "HD": "Consumer Discretionary", "KO": "Consumer Staples", "PFE": "Healthcare",
    "VZ": "Communication", "DIS": "Communication", "NFLX": "Communication",
    "SPY": "Index", "QQQ": "Index", "VTI": "Index", "BND": "Bonds",
    "AGG": "Bonds", "TLT": "Bonds", "GLD": "Commodities", "SLV": "Commodities",
}

RISK_PROFILES = {
    "conservative": {"stocks_max": 40, "bonds_min": 40, "recommended_sectors": 5},
    "moderate": {"stocks_max": 70, "bonds_min": 20, "recommended_sectors": 4},
    "aggressive": {"stocks_max": 95, "bonds_min": 5, "recommended_sectors": 3},
}


def analyze_portfolio(holdings: list, risk_tolerance: str = "moderate") -> dict:
    """Analyze portfolio diversification and provide recommendations."""
    total_allocation = sum(h.get("allocation_pct", 0) for h in holdings)

    # Sector breakdown
    sector_allocation = {}
    for h in holdings:
        ticker = h.get("ticker", "").upper()
        sector = SECTOR_MAP.get(ticker, "Other")
        pct = h.get("allocation_pct", 0)
        sector_allocation[sector] = sector_allocation.get(sector, 0) + pct

    # Concentration analysis
    top_holding = max(holdings, key=lambda x: x.get("allocation_pct", 0)) if holdings else {}
    top_sector = max(sector_allocation.items(), key=lambda x: x[1]) if sector_allocation else ("None", 0)

    # Diversification score (0-100)
    n_holdings = len(holdings)
    n_sectors = len(sector_allocation)
    max_concentration = max((h.get("allocation_pct", 0) for h in holdings), default=0)
    hhi = sum((h.get("allocation_pct", 0) / max(total_allocation, 1) * 100) ** 2 for h in holdings)

    diversification_score = min(100, max(0,
        (min(n_holdings, 20) / 20 * 25) +
        (min(n_sectors, 8) / 8 * 25) +
        ((100 - max_concentration) / 100 * 25) +
        ((10000 - min(hhi, 10000)) / 10000 * 25)
    ))

    # Risk assessment
    risk_profile = RISK_PROFILES.get(risk_tolerance, RISK_PROFILES["moderate"])
    stock_allocation = sum(v for k, v in sector_allocation.items() if k not in ["Bonds", "Commodities", "Index"])
    bond_allocation = sector_allocation.get("Bonds", 0)

    warnings = []
    recommendations = []

    if max_concentration > 30:
        warnings.append(f"High concentration: {top_holding.get('ticker', '?')} at {max_concentration:.1f}%")
        recommendations.append(f"Consider reducing {top_holding.get('ticker', '?')} below 25%")

    if n_sectors < 3:
        warnings.append(f"Low sector diversity: only {n_sectors} sectors")
        recommendations.append("Add exposure to more sectors for better diversification")

    if stock_allocation > risk_profile["stocks_max"]:
        warnings.append(f"Stock allocation ({stock_allocation:.1f}%) exceeds {risk_tolerance} target ({risk_profile['stocks_max']}%)")
        recommendations.append("Consider adding bonds or fixed-income assets")

    if bond_allocation < risk_profile["bonds_min"]:
        recommendations.append(f"Bond allocation ({bond_allocation:.1f}%) is below {risk_tolerance} target ({risk_profile['bonds_min']}%)")

    if not warnings:
        recommendations.append("Portfolio is well-diversified for your risk tolerance")

    return {
        "total_allocation_pct": round(total_allocation, 2),
        "num_holdings": n_holdings,
        "num_sectors": n_sectors,
        "sector_breakdown": {k: round(v, 2) for k, v in sorted(sector_allocation.items(), key=lambda x: x[1], reverse=True)},
        "top_holding": {"ticker": top_holding.get("ticker", "N/A"), "allocation_pct": top_holding.get("allocation_pct", 0)},
        "top_sector": {"name": top_sector[0], "allocation_pct": round(top_sector[1], 2)},
        "diversification_score": round(diversification_score, 1),
        "herfindahl_index": round(hhi, 1),
        "risk_tolerance": risk_tolerance,
        "warnings": warnings,
        "recommendations": recommendations,
    }
