# Fraud Detection Streaming System

Real-time fraud detection using Isolation Forest + XGBoost ensemble on AWS.

## Architecture

- **Kinesis**: Transaction stream ingestion
- **Lambda**: Feature enrichment (velocity, user profile lookups)
- **SageMaker**: Anomaly scoring + classification ensemble
- **DynamoDB**: User profiles and transaction log
- **SNS**: Real-time fraud alerts

## Model

- **Isolation Forest**: Anomaly scoring (unsupervised)
- **XGBoost**: Classification with anomaly score as input feature
- Ensemble approach catches both known patterns and novel anomalies

## Setup

```bash
pip install -r requirements.txt
python -m fraud_detection.train
python -m fraud_detection.simulator --stream fraud-detection-stream --tps 5
sam build && sam deploy --guided
```

## Testing

```bash
pytest fraud_detection/tests/ -v
```
