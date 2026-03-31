"""
Trade Executor Module - Order Execution via Alpaca API.
Handles position sizing, order placement, and stop-loss management.
"""

import os
import json
import logging
from datetime import datetime, timezone
from typing import Optional
import requests
import boto3

logger = logging.getLogger(__name__)


class TradeExecutor:
    PAPER_URL = "https://paper-api.alpaca.markets"
    LIVE_URL = "https://api.alpaca.markets"

    def __init__(self, api_key: str, api_secret: str, paper: bool = True):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = self.PAPER_URL if paper else self.LIVE_URL
        self.paper = paper
        self.headers = {
            "APCA-API-KEY-ID": api_key,
            "APCA-API-SECRET-KEY": api_secret,
            "Content-Type": "application/json",
        }

    def get_account(self) -> dict:
        url = f"{self.base_url}/v2/account"
        response = requests.get(url, headers=self.headers, timeout=30)
        response.raise_for_status()
        return response.json()

    def get_positions(self) -> list:
        url = f"{self.base_url}/v2/positions"
        response = requests.get(url, headers=self.headers, timeout=30)
        response.raise_for_status()
        return response.json()

    def get_position(self, symbol: str) -> Optional[dict]:
        url = f"{self.base_url}/v2/positions/{symbol}"
        response = requests.get(url, headers=self.headers, timeout=30)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    def calculate_position_size(self, equity: float, price: float, position_size_pct: float = 0.02) -> int:
        risk_amount = equity * position_size_pct
        shares = int(risk_amount / price)
        return max(shares, 1)

    def submit_order(self, symbol: str, qty: int, side: str, order_type: str = "market",
                     time_in_force: str = "day", limit_price: Optional[float] = None,
                     stop_price: Optional[float] = None) -> dict:
        url = f"{self.base_url}/v2/orders"
        payload = {"symbol": symbol, "qty": str(qty), "side": side,
                   "type": order_type, "time_in_force": time_in_force}
        if limit_price is not None:
            payload["limit_price"] = str(limit_price)
        if stop_price is not None:
            payload["stop_price"] = str(stop_price)

        logger.info(f"Submitting order: {payload}")
        response = requests.post(url, headers=self.headers, json=payload, timeout=30)
        response.raise_for_status()
        order = response.json()
        logger.info(f"Order submitted: {order['id']} - {side} {qty} {symbol}")
        return order

    def submit_bracket_order(self, symbol: str, qty: int, side: str,
                             take_profit_price: float, stop_loss_price: float,
                             time_in_force: str = "gtc") -> dict:
        url = f"{self.base_url}/v2/orders"
        payload = {
            "symbol": symbol, "qty": str(qty), "side": side, "type": "market",
            "time_in_force": time_in_force, "order_class": "bracket",
            "take_profit": {"limit_price": str(take_profit_price)},
            "stop_loss": {"stop_price": str(stop_loss_price)},
        }
        response = requests.post(url, headers=self.headers, json=payload, timeout=30)
        response.raise_for_status()
        return response.json()

    def cancel_order(self, order_id: str) -> bool:
        url = f"{self.base_url}/v2/orders/{order_id}"
        response = requests.delete(url, headers=self.headers, timeout=30)
        return response.status_code == 204

    def close_position(self, symbol: str) -> dict:
        url = f"{self.base_url}/v2/positions/{symbol}"
        response = requests.delete(url, headers=self.headers, timeout=30)
        response.raise_for_status()
        return response.json()

    def close_all_positions(self) -> list:
        url = f"{self.base_url}/v2/positions"
        response = requests.delete(url, headers=self.headers, timeout=30)
        response.raise_for_status()
        return response.json()

    def is_market_open(self) -> bool:
        url = f"{self.base_url}/v2/clock"
        response = requests.get(url, headers=self.headers, timeout=30)
        response.raise_for_status()
        return response.json().get("is_open", False)


class TradeLogger:
    def __init__(self, table_name: str, region: str = "us-east-1"):
        self.dynamodb = boto3.resource("dynamodb", region_name=region)
        self.table = self.dynamodb.Table(table_name)

    def log_trade(self, symbol: str, signal: str, reason: str, shares: int,
                  price: float, order_id: str = "", indicators: dict = None) -> dict:
        timestamp = datetime.now(timezone.utc).isoformat()
        item = {
            "trade_id": f"{symbol}-{timestamp}",
            "timestamp": timestamp, "symbol": symbol, "signal": signal,
            "reason": reason, "shares": shares, "price": str(price),
            "order_id": order_id, "indicators": json.dumps(indicators or {}),
            "notional_value": str(round(shares * price, 2)),
        }
        self.table.put_item(Item=item)
        logger.info(f"Trade logged: {item['trade_id']}")
        return item

    def get_trades(self, symbol: str = None, limit: int = 100) -> list:
        if symbol:
            response = self.table.query(
                KeyConditionExpression=boto3.dynamodb.conditions.Key("symbol").eq(symbol),
                Limit=limit, ScanIndexForward=False,
            )
        else:
            response = self.table.scan(Limit=limit)
        return response.get("Items", [])


def send_trade_alert(sns_topic_arn: str, trade: dict, region: str = "us-east-1"):
    if not sns_topic_arn:
        return
    sns = boto3.client("sns", region_name=region)
    message = (
        f"Trade Alert\nSymbol: {trade['symbol']}\nSignal: {trade['signal']}\n"
        f"Shares: {trade['shares']}\nPrice: ${trade['price']}\n"
        f"Reason: {trade['reason']}\nTime: {trade['timestamp']}"
    )
    sns.publish(TopicArn=sns_topic_arn, Subject=f"Trading Bot: {trade['signal']} {trade['symbol']}", Message=message)
