# Time-Series Revenue Forecasting

Revenue forecasting using AWS SageMaker DeepAR with automated retraining.

## Features

- Multi-series forecasting (multiple product lines)
- DeepAR algorithm with probabilistic forecasts (confidence intervals)
- Automated weekly retraining via EventBridge
- Baseline comparison (naive, seasonal naive, moving average)
- REST API for on-demand forecasts

## Setup

```bash
pip install -r requirements.txt
python -m revenue_forecast.data_prep    # Generate training data
python -m revenue_forecast.evaluate     # Run baseline backtests
sam build && sam deploy --guided
```

## Testing

```bash
pytest revenue_forecast/tests/ -v
```
