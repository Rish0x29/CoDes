# Algorithmic Trading Bot

Automated trading bot using SMA Crossover + RSI strategy, deployed on AWS Lambda.

## Strategy

- **Entry**: SMA-20 crosses above SMA-50 AND RSI(14) < 70
- **Exit**: SMA-20 crosses below SMA-50 OR RSI(14) > 80 OR stop-loss at -2%
- **Position Sizing**: Fixed fractional (2% of portfolio per trade)

## Architecture

- **AWS Lambda**: Executes strategy on a 1-minute schedule during market hours
- **EventBridge**: Cron trigger (MON-FRI, market hours)
- **DynamoDB**: Trade log persistence
- **Secrets Manager**: API key storage
- **CloudWatch**: Monitoring and alerts
- **SNS**: Trade notifications

## Setup

1. **Install dependencies**: `pip install -r requirements.txt`
2. **Configure**: Edit `config.yaml` with your tickers and strategy parameters
3. **Set API keys**: Store in AWS Secrets Manager or set env vars:
   ```
   export ALPACA_API_KEY=your_key
   export ALPACA_API_SECRET=your_secret
   ```
4. **Deploy**: `sam build && sam deploy --guided`

## Backtesting

```bash
python -m trading_bot.backtest
```

## Testing

```bash
pytest trading_bot/tests/ -v --cov=trading_bot
```

## Files

| File | Description |
|------|-------------|
| `strategy.py` | SMA crossover + RSI signal generation |
| `data_fetcher.py` | Market data from Alpaca / Alpha Vantage |
| `executor.py` | Order execution and trade logging |
| `backtest.py` | Historical backtesting engine |
| `lambda_handler.py` | AWS Lambda entry point |
| `template.yaml` | AWS SAM deployment template |
| `config.yaml` | Strategy and portfolio configuration |
