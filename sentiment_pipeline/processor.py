"""
Sentiment Processor Lambda - Reads from Kinesis, analyzes with Comprehend.
Writes enriched records to Firehose for S3 storage.
"""

import os
import json
import base64
import logging
from datetime import datetime, timezone

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

comprehend = boto3.client("comprehend", region_name=os.environ.get("AWS_REGION", "us-east-1"))
firehose = boto3.client("firehose", region_name=os.environ.get("AWS_REGION", "us-east-1"))

FIREHOSE_STREAM = os.environ.get("FIREHOSE_STREAM", "sentiment-pipeline-firehose")
MAX_TEXT_BYTES = 5000


def analyze_sentiment(text: str) -> dict:
    if not text or not text.strip():
        return {"sentiment": "NEUTRAL", "scores": {}, "error": "Empty text"}

    truncated = text[:MAX_TEXT_BYTES]

    try:
        response = comprehend.detect_sentiment(Text=truncated, LanguageCode="en")
        return {
            "sentiment": response["Sentiment"],
            "scores": {
                "positive": response["SentimentScore"]["Positive"],
                "negative": response["SentimentScore"]["Negative"],
                "neutral": response["SentimentScore"]["Neutral"],
                "mixed": response["SentimentScore"]["Mixed"],
            },
        }
    except Exception as e:
        logger.error(f"Comprehend sentiment error: {e}")
        return {"sentiment": "UNKNOWN", "scores": {}, "error": str(e)}


def extract_entities(text: str) -> list:
    if not text or not text.strip():
        return []

    truncated = text[:MAX_TEXT_BYTES]

    try:
        response = comprehend.detect_entities(Text=truncated, LanguageCode="en")
        entities = []
        seen = set()
        for entity in response.get("Entities", []):
            key = (entity["Text"].lower(), entity["Type"])
            if key not in seen and entity["Score"] >= 0.8:
                entities.append({
                    "text": entity["Text"],
                    "type": entity["Type"],
                    "score": round(entity["Score"], 4),
                })
                seen.add(key)
        return entities
    except Exception as e:
        logger.error(f"Comprehend entities error: {e}")
        return []


def detect_key_phrases(text: str) -> list:
    if not text or not text.strip():
        return []

    truncated = text[:MAX_TEXT_BYTES]

    try:
        response = comprehend.detect_key_phrases(Text=truncated, LanguageCode="en")
        return [
            {"text": kp["Text"], "score": round(kp["Score"], 4)}
            for kp in response.get("KeyPhrases", [])
            if kp["Score"] >= 0.9
        ][:10]
    except Exception as e:
        logger.error(f"Comprehend key phrases error: {e}")
        return []


def detect_language(text: str) -> str:
    if not text or not text.strip():
        return "en"
    try:
        response = comprehend.detect_dominant_language(Text=text[:MAX_TEXT_BYTES])
        languages = response.get("Languages", [])
        if languages:
            return languages[0]["LanguageCode"]
        return "unknown"
    except Exception:
        return "unknown"


def process_record(record: dict) -> dict:
    text = record.get("text", "")
    sentiment_result = analyze_sentiment(text)
    entities = extract_entities(text)
    key_phrases = detect_key_phrases(text)
    language = detect_language(text)

    enriched = {
        **record,
        "sentiment": sentiment_result["sentiment"],
        "sentiment_scores": sentiment_result["scores"],
        "entities": entities,
        "key_phrases": key_phrases,
        "language": language,
        "entity_count": len(entities),
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "year": datetime.now(timezone.utc).strftime("%Y"),
        "month": datetime.now(timezone.utc).strftime("%m"),
        "day": datetime.now(timezone.utc).strftime("%d"),
    }
    return enriched


def send_to_firehose(records: list):
    if not records:
        return

    batch_size = 500
    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]
        firehose_records = [
            {"Data": (json.dumps(r) + "\n").encode("utf-8")}
            for r in batch
        ]
        try:
            response = firehose.put_record_batch(
                DeliveryStreamName=FIREHOSE_STREAM,
                Records=firehose_records,
            )
            failed = response.get("FailedPutCount", 0)
            if failed > 0:
                logger.warning(f"Failed to deliver {failed} records to Firehose")
        except Exception as e:
            logger.error(f"Firehose error: {e}")


def handler(event, context):
    """Lambda handler for Kinesis stream events."""
    logger.info(f"Processing {len(event.get('Records', []))} records")

    enriched_records = []
    errors = 0

    for record in event.get("Records", []):
        try:
            payload = base64.b64decode(record["kinesis"]["data"]).decode("utf-8")
            data = json.loads(payload)
            enriched = process_record(data)
            enriched_records.append(enriched)
        except Exception as e:
            errors += 1
            logger.error(f"Error processing record: {e}", exc_info=True)

    if enriched_records:
        send_to_firehose(enriched_records)

    sentiment_counts = {}
    for r in enriched_records:
        s = r.get("sentiment", "UNKNOWN")
        sentiment_counts[s] = sentiment_counts.get(s, 0) + 1

    result = {
        "processed": len(enriched_records),
        "errors": errors,
        "sentiment_distribution": sentiment_counts,
    }
    logger.info(f"Result: {json.dumps(result)}")
    return result
