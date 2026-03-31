# Credit Risk Scoring API

ML-powered credit risk assessment using XGBoost on AWS SageMaker with REST API.

## Features

- XGBoost model trained on credit data with 19+ features
- Feature engineering pipeline (derived ratios, risk composites)
- Real-time scoring via API Gateway + SageMaker endpoint
- Risk categories: LOW / MEDIUM / HIGH with probability scores

## Setup

```bash
pip install -r requirements.txt
python -m credit_risk.train --model-dir model
python -m credit_risk.evaluate
sam build && sam deploy --guided
```

## API Usage

```bash
curl -X POST https://api-url/prod/score \
  -H "Content-Type: application/json" \
  -d '{"annual_income": 75000, "credit_score": 720, ...}'
```

## Testing

```bash
pytest credit_risk/tests/ -v
```
