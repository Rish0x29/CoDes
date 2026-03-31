"""
Data Fetcher Module - Market Data Ingestion.
Supports Alpaca and Alpha Vantage APIs for OHLCV data.
"""

import os
import json
import logging
from typing import Optional
import pandas as pd
import numpy as np
import requests
import boto3

logger = logging.getLogger(__name__)


class AlpacaDataFetcher:
    BASE_URL_PAPER = "https://paper-api.alpaca.markets"
    BASE_URL_LIVE = "https://api.alpaca.markets"
    DATA_URL = "https://data.alpaca.markets/v2"

    def __init__(self, api_key: str, api_secret: str, paper: bool = True):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = self.BASE_URL_PAPER if paper else self.BASE_URL_LIVE
        self.headers = {
            "APCA-API-KEY-ID": api_key,
            "APCA-API-SECRET-KEY": api_secret,
        }

    def get_bars(self, symbol: str, timeframe: str = "1Day", start: Optional[str] = None,
                 end: Optional[str] = None, limit: int = 1000) -> pd.DataFrame:
        url = f"{self.DATA_URL}/stocks/{symbol}/bars"
        params = {"timeframe": timeframe, "limit": limit}
        if start:
            params["start"] = start
        if end:
            params["end"] = end

        all_bars = []
        page_token = None

        while True:
            if page_token:
                params["page_token"] = page_token
            response = requests.get(url, headers=self.headers, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            bars = data.get("bars", [])
            if bars:
                all_bars.extend(bars)
            page_token = data.get("next_page_token")
            if not page_token:
                break

        if not all_bars:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        df = pd.DataFrame(all_bars)
        df = df.rename(columns={"t": "timestamp", "o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"})
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.set_index("timestamp").sort_index()
        return df[["open", "high", "low", "close", "volume"]]

    def get_latest_bar(self, symbol: str) -> dict:
        url = f"{self.DATA_URL}/stocks/{symbol}/bars/latest"
        response = requests.get(url, headers=self.headers, timeout=30)
        response.raise_for_status()
        bar = response.json().get("bar", {})
        return {"timestamp": bar.get("t"), "open": bar.get("o"), "high": bar.get("h"),
                "low": bar.get("l"), "close": bar.get("c"), "volume": bar.get("v")}

    def get_account(self) -> dict:
        url = f"{self.base_url}/v2/account"
        response = requests.get(url, headers=self.headers, timeout=30)
        response.raise_for_status()
        return response.json()


class AlphaVantageDataFetcher:
    BASE_URL = "https://www.alphavantage.co/query"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def get_daily(self, symbol: str, outputsize: str = "full") -> pd.DataFrame:
        params = {"function": "TIME_SERIES_DAILY", "symbol": symbol,
                  "outputsize": outputsize, "apikey": self.api_key}
        response = requests.get(self.BASE_URL, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        ts = data.get("Time Series (Daily)", {})
        if not ts:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        records = []
        for date_str, values in ts.items():
            records.append({
                "timestamp": pd.Timestamp(date_str),
                "open": float(values["1. open"]), "high": float(values["2. high"]),
                "low": float(values["3. low"]), "close": float(values["4. close"]),
                "volume": int(values["5. volume"]),
            })
        df = pd.DataFrame(records).set_index("timestamp").sort_index()
        return df

    def get_intraday(self, symbol: str, interval: str = "5min", outputsize: str = "full") -> pd.DataFrame:
        params = {"function": "TIME_SERIES_INTRADAY", "symbol": symbol,
                  "interval": interval, "outputsize": outputsize, "apikey": self.api_key}
        response = requests.get(self.BASE_URL, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        key = f"Time Series ({interval})"
        ts = data.get(key, {})
        if not ts:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        records = []
        for date_str, values in ts.items():
            records.append({
                "timestamp": pd.Timestamp(date_str),
                "open": float(values["1. open"]), "high": float(values["2. high"]),
                "low": float(values["3. low"]), "close": float(values["4. close"]),
                "volume": int(values["5. volume"]),
            })
        df = pd.DataFrame(records).set_index("timestamp").sort_index()
        return df


def get_api_keys_from_secrets_manager(secret_name: str, region: str = "us-east-1") -> dict:
    client = boto3.client("secretsmanager", region_name=region)
    response = client.get_secret_value(SecretId=secret_name)
    return json.loads(response["SecretString"])


def create_data_fetcher(config: dict):
    provider = config.get("data", {}).get("provider", "alpaca")
    try:
        secrets = get_api_keys_from_secrets_manager(config["aws"]["secrets_name"], config["aws"]["region"])
    except Exception:
        logger.info("Secrets Manager unavailable, falling back to env vars")
        secrets = {}

    if provider == "alpaca":
        api_key = secrets.get("alpaca_api_key", os.environ.get("ALPACA_API_KEY", ""))
        api_secret = secrets.get("alpaca_api_secret", os.environ.get("ALPACA_API_SECRET", ""))
        paper = config.get("portfolio", {}).get("mode", "paper") == "paper"
        return AlpacaDataFetcher(api_key, api_secret, paper=paper)
    elif provider == "alpha_vantage":
        api_key = secrets.get("alpha_vantage_key", os.environ.get("ALPHA_VANTAGE_KEY", ""))
        return AlphaVantageDataFetcher(api_key)
    else:
        raise ValueError(f"Unknown data provider: {provider}")


def generate_sample_data(symbol: str = "SAMPLE", days: int = 120, start_price: float = 150.0,
                         volatility: float = 0.02, seed: int = 42) -> pd.DataFrame:
    rng = np.random.RandomState(seed)
    dates = pd.bdate_range(end=pd.Timestamp.now().normalize(), periods=days)
    prices = [start_price]
    for i in range(1, days):
        trend = 0.0002 * np.sin(2 * np.pi * i / 60)
        shock = rng.normal(0, volatility)
        mean_revert = -0.001 * (prices[-1] - start_price) / start_price
        change = trend + shock + mean_revert
        prices.append(prices[-1] * (1 + change))

    closes = np.array(prices)
    highs = closes * (1 + rng.uniform(0.001, 0.015, days))
    lows = closes * (1 - rng.uniform(0.001, 0.015, days))
    opens = lows + (highs - lows) * rng.uniform(0.2, 0.8, days)
    volumes = (rng.lognormal(mean=15, sigma=0.5, size=days)).astype(int)

    df = pd.DataFrame({"open": opens.round(2), "high": highs.round(2), "low": lows.round(2),
                        "close": closes.round(2), "volume": volumes}, index=dates)
    df.index.name = "timestamp"
    return df
