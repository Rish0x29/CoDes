"""Feature enrichment Lambda for real-time fraud detection."""

import os
import json
import base64
import logging
from datetime import datetime, timezone
from decimal import Decimal

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
sagemaker = boto3.client("sagemaker-runtime", region_name=os.environ.get("AWS_REGION", "us-east-1"))
sns = boto3.client("sns", region_name=os.environ.get("AWS_REGION", "us-east-1"))

USER_PROFILES_TABLE = os.environ.get("USER_PROFILES_TABLE", "fraud-user-profiles")
TRANSACTIONS_TABLE = os.environ.get("TRANSACTIONS_TABLE", "fraud-transactions")
ENDPOINT_NAME = os.environ.get("SAGEMAKER_ENDPOINT", "fraud-detection-endpoint")
SNS_TOPIC = os.environ.get("SNS_TOPIC_ARN", "")
FRAUD_THRESHOLD = float(os.environ.get("FRAUD_THRESHOLD", "0.7"))


def get_user_profile(customer_id: str) -> dict:
    """Lookup user profile and history from DynamoDB."""
    table = dynamodb.Table(USER_PROFILES_TABLE)
    try:
        response = table.get_item(Key={"customer_id": customer_id})
        return response.get("Item", {})
    except Exception as e:
        logger.warning(f"Could not fetch profile for {customer_id}: {e}")
        return {}


def compute_velocity_features(customer_id: str, current_amount: float) -> dict:
    """Compute transaction velocity features."""
    table = dynamodb.Table(TRANSACTIONS_TABLE)
    try:
        response = table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key("customer_id").eq(customer_id),
            Limit=50, ScanIndexForward=False,
        )
        recent_txns = response.get("Items", [])
    except Exception:
        recent_txns = []

    now = datetime.now(timezone.utc)
    txn_1h = 0
    txn_24h = 0
    amounts_30d = []

    for txn in recent_txns:
        try:
            txn_time = datetime.fromisoformat(txn.get("timestamp", ""))
            delta = (now - txn_time).total_seconds()
            amt = float(txn.get("amount", 0))
            if delta <= 3600:
                txn_1h += 1
            if delta <= 86400:
                txn_24h += 1
            if delta <= 2592000:
                amounts_30d.append(amt)
        except (ValueError, TypeError):
            continue

    avg_amount_30d = sum(amounts_30d) / len(amounts_30d) if amounts_30d else current_amount

    return {
        "txn_count_1h": txn_1h,
        "txn_count_24h": txn_24h,
        "avg_amount_30d": round(avg_amount_30d, 2),
    }


def enrich_transaction(txn: dict) -> dict:
    """Add features to a raw transaction."""
    customer_id = txn.get("customer_id", "unknown")
    amount = float(txn.get("amount", 0))

    profile = get_user_profile(customer_id)
    velocity = compute_velocity_features(customer_id, amount)

    now = datetime.now(timezone.utc)
    enriched = {
        **txn,
        "hour_of_day": now.hour,
        "day_of_week": now.weekday(),
        "distance_from_home": float(txn.get("distance_from_home", 0)),
        "distance_from_last_txn": float(txn.get("distance_from_last_txn", 0)),
        "txn_count_1h": velocity["txn_count_1h"],
        "txn_count_24h": velocity["txn_count_24h"],
        "avg_amount_30d": velocity["avg_amount_30d"],
        "card_present": int(txn.get("card_present", 1)),
        "international": int(txn.get("international", 0)),
        "amount_vs_avg": round(amount / max(velocity["avg_amount_30d"], 1), 4),
        "velocity_1h": velocity["txn_count_1h"] * amount,
        "is_night": int(now.hour >= 23 or now.hour <= 5),
        "is_weekend": int(now.weekday() >= 5),
        "high_amount_flag": int(amount > velocity["avg_amount_30d"] * 3),
        "merchant_category": txn.get("merchant_category", "other"),
        "enriched_at": now.isoformat(),
    }
    return enriched


def score_transaction(enriched: dict) -> float:
    """Score enriched transaction using SageMaker endpoint."""
    try:
        response = sagemaker.invoke_endpoint(
            EndpointName=ENDPOINT_NAME,
            ContentType="application/json",
            Body=json.dumps(enriched),
        )
        result = json.loads(response["Body"].read().decode("utf-8"))
        return float(result.get("fraud_probability", 0))
    except Exception as e:
        logger.error(f"SageMaker scoring error: {e}")
        return 0.0


def log_transaction(txn: dict, fraud_score: float, is_flagged: bool):
    """Store transaction in DynamoDB."""
    table = dynamodb.Table(TRANSACTIONS_TABLE)
    item = {
        "customer_id": txn.get("customer_id", "unknown"),
        "timestamp": txn.get("enriched_at", datetime.now(timezone.utc).isoformat()),
        "transaction_id": txn.get("transaction_id", ""),
        "amount": Decimal(str(round(float(txn.get("amount", 0)), 2))),
        "fraud_score": Decimal(str(round(fraud_score, 4))),
        "is_flagged": is_flagged,
        "merchant_category": txn.get("merchant_category", ""),
    }
    table.put_item(Item=item)


def send_fraud_alert(txn: dict, fraud_score: float):
    """Send SNS alert for flagged transaction."""
    if not SNS_TOPIC:
        return
    message = (
        f"FRAUD ALERT\n"
        f"Transaction: {txn.get('transaction_id', 'N/A')}\n"
        f"Customer: {txn.get('customer_id', 'N/A')}\n"
        f"Amount: ${float(txn.get('amount', 0)):,.2f}\n"
        f"Fraud Score: {fraud_score:.2%}\n"
        f"Category: {txn.get('merchant_category', 'N/A')}\n"
        f"Card Present: {'Yes' if txn.get('card_present') else 'No'}\n"
        f"International: {'Yes' if txn.get('international') else 'No'}\n"
        f"Time: {txn.get('enriched_at', 'N/A')}"
    )
    sns.publish(TopicArn=SNS_TOPIC, Subject="Fraud Alert - Suspicious Transaction", Message=message)


def handler(event, context):
    """Lambda handler for Kinesis stream events."""
    results = {"processed": 0, "flagged": 0, "approved": 0, "errors": 0}

    for record in event.get("Records", []):
        try:
            payload = base64.b64decode(record["kinesis"]["data"]).decode("utf-8")
            txn = json.loads(payload)

            enriched = enrich_transaction(txn)
            fraud_score = score_transaction(enriched)
            is_flagged = fraud_score >= FRAUD_THRESHOLD

            log_transaction(enriched, fraud_score, is_flagged)

            if is_flagged:
                send_fraud_alert(enriched, fraud_score)
                results["flagged"] += 1
                logger.warning(f"FLAGGED: {txn.get('transaction_id')} score={fraud_score:.4f}")
            else:
                results["approved"] += 1

            results["processed"] += 1

        except Exception as e:
            logger.error(f"Error processing record: {e}", exc_info=True)
            results["errors"] += 1

    logger.info(f"Results: {json.dumps(results)}")
    return results
