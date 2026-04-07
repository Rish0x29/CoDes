"""
lvr_tracker.py
──────────────────────────────────────────────────────────────────────────────
LVR (Loss-Versus-Rebalancing) Tracker for Uniswap V3 Positions

Computes the true profitability of a concentrated liquidity position against
the counterfactual of simply holding the same assets. Separates:

  • Impermanent Loss (IL)  — path-independent rebalancing loss
  • LVR                    — path-dependent loss from arbitrageur extraction
  • Fee Income             — gross fee revenue while in-range
  • Net LP Alpha           — LP PnL minus buy-and-hold PnL

Theory:
  LVR ≈ ½ · σ² · γ(p) · V · dt  per infinitesimal interval
  where γ(p) = 1 / (√p_b - √p_a) · p / (√p · (√p_b - √p_a))
  is the effective "gamma" (curvature) of the V3 AMM payoff.

  IL_v3(p_final) = 2·√(p_final/p_0)/(1 + p_final/p_0) - 1
  (applies only while position is in-range; once out-of-range, IL is frozen)

Usage:
  python lvr_tracker.py                    # demo with synthetic data
  python lvr_tracker.py --pool ETH/USDC   # specific pool with live Subgraph data
  python lvr_tracker.py --csv prices.csv  # custom price CSV

Requirements:
  pip install numpy pandas matplotlib requests python-dotenv tqdm
"""

import argparse
import json
import math
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.ticker import FuncFormatter


# ──────────────────────────────────────────────────────────────────────────────
#  Constants & Config
# ──────────────────────────────────────────────────────────────────────────────

UNISWAP_V3_SUBGRAPH = (
    "https://api.thegraph.com/subgraphs/name/uniswap/uniswap-v3"
)

# Known pools (address → fee tier in bps)
KNOWN_POOLS = {
    "ETH/USDC":   {"address": "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640", "fee": 5},
    "ETH/USDC-30":{"address": "0x8ad599c3a0ff1de082011efddc58f1908eb6e6d8", "fee": 30},
    "WBTC/ETH":   {"address": "0xcbcdf9626bc03e24f779434178a73a0b4bad62ed", "fee": 30},
    "DAI/USDC":   {"address": "0x5777d92f208679db4b9778590fa3cab3ac9e2168", "fee": 1},
}

DOLLAR = FuncFormatter(lambda x, _: f"${x:,.0f}")
PCT    = FuncFormatter(lambda x, _: f"{x:.1f}%")


# ──────────────────────────────────────────────────────────────────────────────
#  Data Classes
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class PositionParams:
    capital_usd:    float = 10_000.0   # total value at entry (USD)
    price_lower:    float = 1_600.0    # Pa — lower tick price
    price_upper:    float = 2_800.0    # Pb — upper tick price
    entry_price:    float = 2_000.0    # p0
    fee_tier_bps:   float = 5.0        # Uniswap fee tier (5 = 0.05%)
    entry_date:     str   = "2024-01-01"
    exit_date:      str   = "2024-12-31"


@dataclass
class LVRResult:
    dates:              list
    prices:             list

    # Cumulative series
    lp_value:           list
    hodl_value:         list
    fee_income:         list
    impermanent_loss:   list
    lvr_cost:           list
    net_alpha:          list

    # Scalars
    total_fees:         float
    total_il:           float
    total_lvr:          float
    final_lp_value:     float
    final_hodl_value:   float
    net_alpha_pct:      float
    in_range_pct:       float
    annualized_apr:     float
    annualized_lvr:     float
    sigma:              float           # realized vol (annualized)
    days:               int


# ──────────────────────────────────────────────────────────────────────────────
#  V3 Math
# ──────────────────────────────────────────────────────────────────────────────

class UniswapV3Math:

    @staticmethod
    def liquidity_from_capital(
        capital: float,
        p0: float,
        pa: float,
        pb: float
    ) -> tuple[float, float, float]:
        """
        Decompose capital into (L, x_amount, y_amount) given range [pa, pb].
        Assumes p0 is within [pa, pb].
        Returns: (liquidity L, token0 amount, token1 amount)
        """
        sp  = math.sqrt(p0)
        spa = math.sqrt(pa)
        spb = math.sqrt(pb)

        # Fraction of value in token0 vs token1 at p0
        # token0_value / total_value = (√pb - √p0) / (√pb - √pa) · fraction
        denom = (sp - spa) / (sp * spa) * p0 + (spb - sp)
        frac0 = ((spb - sp) / denom) if denom > 0 else 0.5

        value0 = capital * frac0
        value1 = capital * (1 - frac0)

        x = value0 / p0
        y = value1

        # Liquidity from token0 side: L = x / (1/√p0 - 1/√pb)
        denom_x = 1/sp - 1/spb
        L = x / denom_x if denom_x > 0 else 0

        return L, x, y

    @staticmethod
    def lp_value(L: float, p: float, pa: float, pb: float) -> float:
        """
        Current portfolio value of an LP position with liquidity L
        at price p, within range [pa, pb].
        """
        sp  = math.sqrt(max(pa, min(p, pb)))
        spa = math.sqrt(pa)
        spb = math.sqrt(pb)

        # token0 amount: L * (1/√p_eff - 1/√pb)
        x = L * (1/sp - 1/spb) if sp < spb else 0
        # token1 amount: L * (√p_eff - √pa)
        y = L * (sp - spa) if sp > spa else 0

        return x * p + y

    @staticmethod
    def impermanent_loss_v3(
        p_current: float,
        p_entry: float,
        pa: float,
        pb: float,
        L: float,
        capital: float
    ) -> float:
        """
        IL = LP_value(p_current) - hodl_value(p_current)
        hodl_value grows with price in proportion to initial allocation.
        Returns IL as negative dollar amount.
        """
        lp_val  = UniswapV3Math.lp_value(L, p_current, pa, pb)

        # Clamp price for LP, but hodl always grows
        sp0 = math.sqrt(p_entry)
        spa = math.sqrt(pa)
        spb = math.sqrt(pb)
        sp0_eff = max(spa, min(sp0, spb))

        x0 = L * (1/sp0_eff - 1/spb) if sp0_eff < spb else 0
        y0 = L * (sp0_eff - spa) if sp0_eff > spa else 0

        hodl_val = x0 * p_current + y0
        return lp_val - hodl_val

    @staticmethod
    def gamma(p: float, pa: float, pb: float) -> float:
        """
        Effective gamma of V3 AMM = curvature of payoff = ∂²V/∂p²
        γ(p) = L / (2 * p^(3/2)) when in range.
        Normalized per unit of capital: γ_norm = 1 / (√pb - √pa)
        """
        if p <= pa or p >= pb:
            return 0.0
        spa = math.sqrt(pa)
        spb = math.sqrt(pb)
        return 1.0 / (2 * math.sqrt(p) * (spb - spa))

    @staticmethod
    def is_in_range(p: float, pa: float, pb: float) -> bool:
        return pa <= p <= pb


# ──────────────────────────────────────────────────────────────────────────────
#  Data Sources
# ──────────────────────────────────────────────────────────────────────────────

def fetch_subgraph_prices(
    pool_address: str,
    start_ts: int,
    end_ts: int
) -> pd.DataFrame:
    """
    Fetch hourly pool price data from Uniswap V3 Subgraph.
    Returns DataFrame with columns: [timestamp, price, volumeUSD].
    """
    query = """
    {
      poolHourDatas(
        first: 1000
        orderBy: periodStartUnix
        orderDirection: asc
        where: {
          pool: "%s"
          periodStartUnix_gte: %d
          periodStartUnix_lte: %d
        }
      ) {
        periodStartUnix
        token0Price
        token1Price
        volumeUSD
        tvlUSD
      }
    }
    """ % (pool_address.lower(), start_ts, end_ts)

    try:
        import requests
        resp = requests.post(
            UNISWAP_V3_SUBGRAPH,
            json={"query": query},
            timeout=15
        )
        data = resp.json()["data"]["poolHourDatas"]
        df = pd.DataFrame(data)
        df["timestamp"] = pd.to_datetime(df["periodStartUnix"].astype(int), unit="s")
        df["price"]     = df["token0Price"].astype(float)
        df["volumeUSD"] = df["volumeUSD"].astype(float)
        df["tvlUSD"]    = df["tvlUSD"].astype(float)
        return df[["timestamp", "price", "volumeUSD", "tvlUSD"]]
    except Exception as e:
        print(f"[warn] Subgraph fetch failed ({e}), using synthetic data")
        return None


def load_csv_prices(path: str) -> pd.DataFrame:
    """Load price data from CSV. Expected columns: date, price, [volumeUSD]"""
    df = pd.read_csv(path, parse_dates=["date"])
    df = df.rename(columns={"date": "timestamp"})
    if "volumeUSD" not in df.columns:
        df["volumeUSD"] = df["price"] * 1e6  # rough estimate
    return df


def generate_synthetic_prices(
    start_date: str,
    end_date: str,
    p0: float = 2000.0,
    sigma_ann: float = 0.85,
    mu_ann: float = 0.30,
    seed: int = 42
) -> pd.DataFrame:
    """
    GBM price simulation for backtesting without live data.
    sigma_ann = annualized vol (ETH ≈ 0.85, BTC ≈ 0.65)
    """
    np.random.seed(seed)
    dates = pd.date_range(start_date, end_date, freq="1h")
    dt    = 1 / 8760  # 1 hour in years

    log_returns = (
        (mu_ann - 0.5 * sigma_ann**2) * dt
        + sigma_ann * math.sqrt(dt) * np.random.randn(len(dates))
    )
    prices = p0 * np.exp(np.cumsum(log_returns))
    prices[0] = p0

    # Synthetic volume: proportional to |price change| * base_volume
    vol_base = p0 * 50_000
    volumes  = vol_base * (1 + 5 * np.abs(np.diff(log_returns, prepend=0)))

    return pd.DataFrame({
        "timestamp": dates,
        "price":     prices,
        "volumeUSD": volumes,
        "tvlUSD":    np.full(len(dates), p0 * 1e5)
    })


# ──────────────────────────────────────────────────────────────────────────────
#  Core Backtester
# ──────────────────────────────────────────────────────────────────────────────

class LVRBacktester:

    def __init__(self, params: PositionParams):
        self.p = params
        self.math = UniswapV3Math()

    def run(self, df: pd.DataFrame) -> LVRResult:
        """
        Main backtest loop. Processes hourly price data.
        Returns LVRResult with all time series and summary stats.
        """
        p  = self.p
        pa = p.price_lower
        pb = p.price_upper
        p0 = p.entry_price
        fee_rate = p.fee_tier_bps / 10_000

        # ── Initialize position ────────────────────────────────────────────
        L, x0, y0 = self.math.liquidity_from_capital(p.capital_usd, p0, pa, pb)

        # ── Filter to backtest window ──────────────────────────────────────
        mask = (df["timestamp"] >= p.entry_date) & (df["timestamp"] <= p.exit_date)
        df   = df[mask].reset_index(drop=True)

        if len(df) < 2:
            raise ValueError("Insufficient data for backtest window")

        # ── Compute realized sigma ─────────────────────────────────────────
        log_rets = np.diff(np.log(df["price"].values))
        sigma_h  = np.std(log_rets)
        sigma_ann = sigma_h * math.sqrt(8760)

        # ── Time series ────────────────────────────────────────────────────
        lp_vals     = []
        hodl_vals   = []
        fee_cum     = []
        il_cum      = []
        lvr_cum     = []
        net_alphas  = []
        in_range_count = 0

        cumulative_fees = 0.0
        cumulative_lvr  = 0.0

        for i, row in df.iterrows():
            price_t = row["price"]
            vol_t   = row.get("volumeUSD", price_t * 1e5)

            in_range = self.math.is_in_range(price_t, pa, pb)
            if in_range:
                in_range_count += 1

            # LP value
            lp_v = self.math.lp_value(L, price_t, pa, pb)

            # Hodl value (hold x0 ETH + y0 USDC)
            hodl_v = x0 * price_t + y0

            # Impermanent loss
            il = self.math.impermanent_loss_v3(price_t, p0, pa, pb, L, p.capital_usd)

            # Fee income (per hour, proportional to vol while in-range)
            if in_range and i > 0:
                # Fee share ≈ fee_rate × (our_liquidity / pool_tvl) × volume
                pool_tvl = max(row.get("tvlUSD", lp_v * 10), lp_v)
                fee_share = (lp_v / pool_tvl) if pool_tvl > 0 else 0.01
                hour_fee = fee_rate * vol_t * fee_share
                cumulative_fees += hour_fee

            # LVR: ½ · σ² · γ(p) · V · dt  (dt = 1 hour = 1/8760 year)
            if in_range:
                gamma_t = self.math.gamma(price_t, pa, pb)
                dt_year = 1 / 8760
                lvr_t   = 0.5 * sigma_h**2 * gamma_t * lp_v * 8760 * dt_year
                cumulative_lvr += lvr_t

            net = (lp_v + cumulative_fees) - hodl_v

            lp_vals.append(lp_v + cumulative_fees)
            hodl_vals.append(hodl_v)
            fee_cum.append(cumulative_fees)
            il_cum.append(il)
            lvr_cum.append(-cumulative_lvr)
            net_alphas.append(net)

        days       = len(df) / 24
        final_lp   = lp_vals[-1]
        final_hodl = hodl_vals[-1]
        net_alpha  = final_lp - final_hodl
        net_pct    = (net_alpha / p.capital_usd) * 100
        apr        = (cumulative_fees / p.capital_usd) * (365 / max(days, 1)) * 100
        lvr_apr    = (cumulative_lvr  / p.capital_usd) * (365 / max(days, 1)) * 100
        in_pct     = (in_range_count / max(len(df), 1)) * 100

        return LVRResult(
            dates=df["timestamp"].tolist(),
            prices=df["price"].tolist(),
            lp_value=lp_vals,
            hodl_value=hodl_vals,
            fee_income=fee_cum,
            impermanent_loss=il_cum,
            lvr_cost=lvr_cum,
            net_alpha=net_alphas,
            total_fees=cumulative_fees,
            total_il=il_cum[-1] if il_cum else 0,
            total_lvr=cumulative_lvr,
            final_lp_value=final_lp,
            final_hodl_value=final_hodl,
            net_alpha_pct=net_pct,
            in_range_pct=in_pct,
            annualized_apr=apr,
            annualized_lvr=lvr_apr,
            sigma=sigma_ann,
            days=int(days),
        )


# ──────────────────────────────────────────────────────────────────────────────
#  Visualization
# ──────────────────────────────────────────────────────────────────────────────

def plot_results(result: LVRResult, params: PositionParams, output: str = None):
    """Generates a 6-panel dashboard figure."""
    fig = plt.figure(figsize=(18, 12), facecolor="#0d1117")
    fig.suptitle(
        "LVR Tracker — Uniswap V3 LP Profitability Analysis",
        color="#e6edf3", fontsize=15, fontweight="bold", y=0.97
    )

    gs = gridspec.GridSpec(3, 3, figure=fig, hspace=0.45, wspace=0.35)
    ax_main   = fig.add_subplot(gs[0, :2])
    ax_price  = fig.add_subplot(gs[0, 2])
    ax_fees   = fig.add_subplot(gs[1, 0])
    ax_lvr    = fig.add_subplot(gs[1, 1])
    ax_net    = fig.add_subplot(gs[1, 2])
    ax_stats  = fig.add_subplot(gs[2, :])

    AXES_BG  = "#161b22"
    GREEN    = "#3fb950"
    RED      = "#f85149"
    BLUE     = "#58a6ff"
    AMBER    = "#e3b341"
    MUTED    = "#8b949e"
    TEXT     = "#c9d1d9"

    def style_ax(ax, title=""):
        ax.set_facecolor(AXES_BG)
        ax.tick_params(colors=MUTED, labelsize=8)
        ax.spines[:].set_color("#30363d")
        if title:
            ax.set_title(title, color=TEXT, fontsize=9, pad=6)

    dates = result.dates

    # ── Panel 1: LP vs HODL ───────────────────────────────────────────────
    style_ax(ax_main, "LP Value vs Buy & Hold")
    ax_main.plot(dates, result.lp_value,   color=GREEN, lw=1.5, label="LP + fees")
    ax_main.plot(dates, result.hodl_value, color=BLUE,  lw=1.2, ls="--", label="Buy & hold")
    ax_main.fill_between(
        dates,
        result.lp_value, result.hodl_value,
        where=[lp >= h for lp, h in zip(result.lp_value, result.hodl_value)],
        alpha=0.15, color=GREEN
    )
    ax_main.fill_between(
        dates,
        result.lp_value, result.hodl_value,
        where=[lp < h for lp, h in zip(result.lp_value, result.hodl_value)],
        alpha=0.15, color=RED
    )
    ax_main.axhline(params.capital_usd, color=MUTED, lw=0.7, ls=":")
    ax_main.yaxis.set_major_formatter(DOLLAR)
    ax_main.legend(facecolor=AXES_BG, edgecolor="#30363d", labelcolor=TEXT, fontsize=8)

    # ── Panel 2: Price + Range ────────────────────────────────────────────
    style_ax(ax_price, "Price & Range Bounds")
    ax_price.plot(dates, result.prices, color=AMBER, lw=1, label="Price")
    ax_price.axhline(params.price_lower, color=RED,   lw=0.8, ls="--", alpha=0.7, label=f"Pa ${params.price_lower:,.0f}")
    ax_price.axhline(params.price_upper, color=GREEN, lw=0.8, ls="--", alpha=0.7, label=f"Pb ${params.price_upper:,.0f}")
    ax_price.fill_between(dates, params.price_lower, params.price_upper, alpha=0.07, color=GREEN)
    ax_price.yaxis.set_major_formatter(DOLLAR)
    ax_price.legend(facecolor=AXES_BG, edgecolor="#30363d", labelcolor=TEXT, fontsize=7)

    # ── Panel 3: Cumulative Fees ──────────────────────────────────────────
    style_ax(ax_fees, "Cumulative Fee Income")
    ax_fees.fill_between(dates, 0, result.fee_income, color=GREEN, alpha=0.4)
    ax_fees.plot(dates, result.fee_income, color=GREEN, lw=1)
    ax_fees.yaxis.set_major_formatter(DOLLAR)

    # ── Panel 4: LVR ─────────────────────────────────────────────────────
    style_ax(ax_lvr, "Cumulative LVR Cost")
    ax_lvr.fill_between(dates, 0, result.lvr_cost, color=RED, alpha=0.4)
    ax_lvr.plot(dates, result.lvr_cost, color=RED, lw=1)
    ax_lvr.yaxis.set_major_formatter(DOLLAR)

    # ── Panel 5: Net Alpha ────────────────────────────────────────────────
    style_ax(ax_net, "Net LP Alpha (LP − Hold)")
    net = result.net_alpha
    colors = [GREEN if v >= 0 else RED for v in net]
    ax_net.fill_between(dates, 0, net, color=GREEN if net[-1] >= 0 else RED, alpha=0.3)
    ax_net.plot(dates, net, color=GREEN if net[-1] >= 0 else RED, lw=1.2)
    ax_net.axhline(0, color=MUTED, lw=0.7)
    ax_net.yaxis.set_major_formatter(DOLLAR)

    # ── Panel 6: Stats Table ──────────────────────────────────────────────
    ax_stats.set_facecolor(AXES_BG)
    ax_stats.axis("off")
    ax_stats.set_title("Summary Statistics", color=TEXT, fontsize=9, pad=6)
    ax_stats.spines[:].set_color("#30363d")

    r = result
    col_labels = ["Metric", "Value", "Metric", "Value", "Metric", "Value"]
    stats = [
        ("Capital deployed",  f"${params.capital_usd:,.0f}"),
        ("Final LP value",    f"${r.final_lp_value:,.0f}"),
        ("Final hodl value",  f"${r.final_hodl_value:,.0f}"),
        ("Net alpha",         f"${r.final_lp_value - r.final_hodl_value:,.0f} ({r.net_alpha_pct:+.1f}%)"),
        ("Fee income",        f"${r.total_fees:,.0f}"),
        ("Annualized APR",    f"{r.annualized_apr:.1f}%"),
        ("Total LVR cost",    f"${r.total_lvr:,.0f}"),
        ("Annualized LVR",    f"{r.annualized_lvr:.1f}%"),
        ("Total IL",          f"${r.total_il:,.0f}"),
        ("In-range %",        f"{r.in_range_pct:.1f}%"),
        ("Realized σ (ann)",  f"{r.sigma:.1%}"),
        ("Backtest days",     f"{r.days}d"),
    ]

    # 4 columns
    rows_per_col = 4
    table_data = []
    for i in range(rows_per_col):
        row = []
        for j in range(3):
            idx = i + j * rows_per_col
            if idx < len(stats):
                row += list(stats[idx])
            else:
                row += ["", ""]
        table_data.append(row)

    tbl = ax_stats.table(
        cellText=table_data,
        colLabels=col_labels,
        cellLoc="left",
        loc="center",
        bbox=[0, -0.1, 1, 1.1]
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(8)
    for (row, col), cell in tbl.get_celld().items():
        cell.set_facecolor(AXES_BG if row > 0 else "#21262d")
        cell.set_edgecolor("#30363d")
        if col % 2 == 0:
            cell.set_text_props(color=MUTED)
        else:
            v = cell.get_text().get_text()
            color = GREEN if any(c in v for c in ["+", "APR"]) and "-" not in v else (RED if "-" in v and "$" in v else TEXT)
            cell.set_text_props(color=color, fontweight="bold" if row == 0 else "normal")

    if output:
        plt.savefig(output, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
        print(f"[✓] Chart saved to {output}")
    else:
        plt.show()


# ──────────────────────────────────────────────────────────────────────────────
#  CLI Entry Point
# ──────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Uniswap V3 LVR Tracker")
    parser.add_argument("--pool",    default="ETH/USDC", choices=list(KNOWN_POOLS.keys()))
    parser.add_argument("--capital", type=float, default=10_000)
    parser.add_argument("--lower",   type=float, default=1_600,   help="Pa (lower price)")
    parser.add_argument("--upper",   type=float, default=2_800,   help="Pb (upper price)")
    parser.add_argument("--entry",   type=float, default=2_000,   help="Entry price")
    parser.add_argument("--start",   default="2024-01-01")
    parser.add_argument("--end",     default="2024-12-31")
    parser.add_argument("--csv",     default=None,                 help="Path to price CSV")
    parser.add_argument("--output",  default="lvr_report.png",    help="Output chart path")
    parser.add_argument("--synthetic", action="store_true",        help="Force synthetic data")
    args = parser.parse_args()

    params = PositionParams(
        capital_usd=args.capital,
        price_lower=args.lower,
        price_upper=args.upper,
        entry_price=args.entry,
        fee_tier_bps=KNOWN_POOLS.get(args.pool, {}).get("fee", 5),
        entry_date=args.start,
        exit_date=args.end,
    )

    print(f"\n{'─'*60}")
    print(f"  LVR Tracker │ {args.pool} │ ${params.capital_usd:,.0f} capital")
    print(f"  Range: ${params.price_lower:,.0f} – ${params.price_upper:,.0f}")
    print(f"  Period: {args.start} → {args.end}")
    print(f"{'─'*60}\n")

    # ── Load Data ──────────────────────────────────────────────────────────
    df = None
    if args.csv:
        print(f"[→] Loading prices from {args.csv}")
        df = load_csv_prices(args.csv)
    elif not args.synthetic:
        pool_info = KNOWN_POOLS.get(args.pool, {})
        if pool_info:
            import datetime as dt
            start_ts = int(dt.datetime.strptime(args.start, "%Y-%m-%d").timestamp())
            end_ts   = int(dt.datetime.strptime(args.end,   "%Y-%m-%d").timestamp())
            print(f"[→] Fetching from Uniswap V3 Subgraph...")
            df = fetch_subgraph_prices(pool_info["address"], start_ts, end_ts)

    if df is None:
        print(f"[→] Using GBM synthetic prices (σ=0.85, μ=0.30)")
        df = generate_synthetic_prices(args.start, args.end, p0=params.entry_price)

    print(f"[✓] Loaded {len(df):,} hourly data points")

    # ── Run Backtest ───────────────────────────────────────────────────────
    backtester = LVRBacktester(params)
    result     = backtester.run(df)

    # ── Print Summary ──────────────────────────────────────────────────────
    sign = lambda v: f"+${v:,.0f}" if v >= 0 else f"-${abs(v):,.0f}"
    print(f"\n{'─'*60}")
    print(f"  RESULTS")
    print(f"{'─'*60}")
    print(f"  Final LP value:     ${result.final_lp_value:>10,.0f}")
    print(f"  Final hodl value:   ${result.final_hodl_value:>10,.0f}")
    print(f"  Net alpha:          {sign(result.final_lp_value - result.final_hodl_value):>10s}  ({result.net_alpha_pct:+.1f}%)")
    print(f"  Fee income:         ${result.total_fees:>10,.0f}  (APR {result.annualized_apr:.1f}%)")
    print(f"  LVR cost:           -${result.total_lvr:>9,.0f}  (APR {result.annualized_lvr:.1f}%)")
    print(f"  Impermanent loss:   ${result.total_il:>10,.0f}")
    print(f"  In-range:           {result.in_range_pct:>9.1f}%")
    print(f"  Realized vol (σ):   {result.sigma:>9.1%}")
    print(f"  Verdict:            {'LP beats hold ✓' if result.net_alpha_pct >= 0 else 'Hold outperforms ✗'}")
    print(f"{'─'*60}\n")

    # ── Plot ───────────────────────────────────────────────────────────────
    plot_results(result, params, output=args.output)


if __name__ == "__main__":
    main()
