# Customer Churn Prediction Dashboard

Predict and prevent customer churn using XGBoost on AWS SageMaker with Glue ETL.

## Pipeline

1. **Data Generation**: Synthetic telco churn dataset (5000+ customers)
2. **Glue ETL**: PySpark job for cleaning, feature engineering
3. **SageMaker Training**: XGBoost with cross-validation
4. **Batch Scoring**: Score all customers with risk tiers
5. **Athena Queries**: Analytics on scored data

## Setup

```bash
pip install -r requirements.txt
python -m churn_prediction.generate_data
python -m churn_prediction.train
python -m churn_prediction.score
```

## Testing

```bash
pytest churn_prediction/tests/ -v
```
