# Conversational AI Financial Advisor Chatbot

AI-powered financial advisor using AWS Bedrock with tool-use for portfolio analysis.

## Features

- Multi-turn conversational AI using Claude on Bedrock
- Portfolio analysis tool (diversification, sector breakdown, recommendations)
- Market data tool (price, P/E, market cap, 52-week range)
- Risk calculation tool (VaR, volatility, Sharpe ratio, drawdown estimates)
- Modern chat UI with conversation history
- DynamoDB-backed conversation persistence

## Deploy

```bash
sam build && sam deploy --guided
```

Upload `frontend/index.html` to the S3 frontend bucket.

## Testing

```bash
pytest financial_chatbot/tests/ -v
```
