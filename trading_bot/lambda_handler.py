"""
AWS Lambda Handler - Entry point for the trading bot.
Triggered by EventBridge on a schedule during market hours.
"""

import os
import json
import logging
import yaml
import boto3
from datetime import datetime, timedelta, timezone

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def load_config() -> dict:
    config_path = os.environ.get("CONFIG_PATH", "config.yaml")
    if os.path.exists(config_path):
        with open(config_path) as f:
            return yaml.safe_load(f)
    return {
        "strategy": {"sma_short_period": 20, "sma_long_period": 50, "rsi_period": 14,
                      "rsi_overbought": 80, "rsi_entry_max": 70, "stop_loss_pct": 0.02},
        "portfolio": {"position_size_pct": 0.02, "max_positions": 5, "mode": "paper"},
        "tickers": ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"],
        "data": {"provider": "alpaca", "candle_interval": "1Day", "lookback_days": 60},
        "aws": {"region": "us-east-1", "dynamodb_table": "trading_bot_trades",
                "secrets_name": "trading_bot/api_keys"},
        "alerts": {"sns_topic_arn": "", "notify_on_trade": True, "notify_on_error": True},
    }


def get_secrets(secret_name: str, region: str) -> dict:
    client = boto3.client("secretsmanager", region_name=region)
    response = client.get_secret_value(SecretId=secret_name)
    return json.loads(response["SecretString"])


def handler(event, context):
    """
    Lambda handler for the trading bot.

    Processes each ticker: fetches data, generates signals, executes trades.
    """
    from trading_bot.strategy import generate_signal, Signal
    from trading_bot.data_fetcher import AlpacaDataFetcher
    from trading_bot.executor import TradeExecutor, TradeLogger, send_trade_alert

    config = load_config()
    region = config["aws"]["region"]

    try:
        secrets = get_secrets(config["aws"]["secrets_name"], region)
        api_key = secrets["alpaca_api_key"]
        api_secret = secrets["alpaca_api_secret"]
    except Exception:
        api_key = os.environ.get("ALPACA_API_KEY", "")
        api_secret = os.environ.get("ALPACA_API_SECRET", "")

    paper = config["portfolio"]["mode"] == "paper"
    fetcher = AlpacaDataFetcher(api_key, api_secret, paper=paper)
    executor = TradeExecutor(api_key, api_secret, paper=paper)
    trade_logger = TradeLogger(config["aws"]["dynamodb_table"], region)

    # Check market hours
    if not executor.is_market_open():
        logger.info("Market is closed. Skipping.")
        return {"statusCode": 200, "body": json.dumps({"message": "Market closed"})}

    # Get account info
    account = executor.get_account()
    equity = float(account["equity"])
    buying_power = float(account["buying_power"])
    logger.info(f"Account equity: ${equity:,.2f}, buying_power: ${buying_power:,.2f}")

    # Get current positions
    positions = executor.get_positions()
    position_map = {p["symbol"]: p for p in positions}

    strategy_config = config["strategy"]
    lookback_days = config["data"]["lookback_days"]
    start_date = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).strftime("%Y-%m-%dT00:00:00Z")

    results = []

    for ticker in config["tickers"]:
        try:
            logger.info(f"Processing {ticker}...")
            df = fetcher.get_bars(ticker, timeframe="1Day", start=start_date, limit=lookback_days)

            if len(df) < strategy_config["sma_long_period"] + 2:
                logger.warning(f"{ticker}: Insufficient data ({len(df)} bars)")
                results.append({"ticker": ticker, "signal": "HOLD", "reason": "Insufficient data"})
                continue

            current_position = None
            if ticker in position_map:
                pos = position_map[ticker]
                current_position = {
                    "entry_price": float(pos["avg_entry_price"]),
                    "shares": int(pos["qty"]),
                    "side": pos["side"],
                }

            result = generate_signal(
                df,
                sma_short_period=strategy_config["sma_short_period"],
                sma_long_period=strategy_config["sma_long_period"],
                rsi_period=strategy_config["rsi_period"],
                rsi_entry_max=strategy_config["rsi_entry_max"],
                rsi_overbought=strategy_config["rsi_overbought"],
                stop_loss_pct=strategy_config["stop_loss_pct"],
                current_position=current_position,
            )

            signal = result["signal"]
            logger.info(f"{ticker}: Signal={signal.value}, Reason={result['reason']}")

            if signal == Signal.BUY:
                if len(position_map) >= config["portfolio"]["max_positions"]:
                    logger.info(f"{ticker}: Max positions reached, skipping BUY")
                    results.append({"ticker": ticker, "signal": "HOLD", "reason": "Max positions reached"})
                    continue

                price = result["indicators"]["close"]
                shares = executor.calculate_position_size(equity, price, config["portfolio"]["position_size_pct"])

                order = executor.submit_order(ticker, shares, "buy")
                trade = trade_logger.log_trade(
                    symbol=ticker, signal="BUY", reason=result["reason"],
                    shares=shares, price=price, order_id=order["id"],
                    indicators=result["indicators"],
                )

                if config["alerts"]["notify_on_trade"] and config["alerts"]["sns_topic_arn"]:
                    send_trade_alert(config["alerts"]["sns_topic_arn"], trade, region)

                results.append({"ticker": ticker, "signal": "BUY", "shares": shares, "order_id": order["id"]})

            elif signal == Signal.SELL and current_position:
                shares = current_position["shares"]
                price = result["indicators"]["close"]

                order = executor.submit_order(ticker, shares, "sell")
                trade = trade_logger.log_trade(
                    symbol=ticker, signal="SELL", reason=result["reason"],
                    shares=shares, price=price, order_id=order["id"],
                    indicators=result["indicators"],
                )

                if config["alerts"]["notify_on_trade"] and config["alerts"]["sns_topic_arn"]:
                    send_trade_alert(config["alerts"]["sns_topic_arn"], trade, region)

                results.append({"ticker": ticker, "signal": "SELL", "shares": shares, "order_id": order["id"]})

            else:
                results.append({"ticker": ticker, "signal": "HOLD", "reason": result["reason"]})

        except Exception as e:
            logger.error(f"Error processing {ticker}: {str(e)}", exc_info=True)
            results.append({"ticker": ticker, "signal": "ERROR", "error": str(e)})

    return {
        "statusCode": 200,
        "body": json.dumps({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "account_equity": equity,
            "positions": len(position_map),
            "results": results,
        }),
    }
