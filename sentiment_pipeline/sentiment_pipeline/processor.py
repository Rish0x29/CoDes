"""
AWS Lambda function that processes records from a Kinesis stream.

For each record:
  1. Decode and parse the JSON payload.
  2. Call AWS Comprehend for sentiment analysis (positive/negative/neutral/mixed
     with confidence scores).
  3. Call AWS Comprehend for entity extraction.
  4. Build an enriched record combining the original data with NLP results.
  5. Write the enriched record to a Kinesis Firehose delivery stream for
     storage in S3.

Environment variables:
  FIREHOSE_STREAM_NAME  - Firehose delivery stream name (default: sentiment-firehose)
  COMPREHEND_LANGUAGE    - Language code for Comprehend (default: en)
"""

import base64
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

FIREHOSE_STREAM_NAME = os.environ.get("FIREHOSE_STREAM_NAME", "sentiment-firehose")
COMPREHEND_LANGUAGE = os.environ.get("COMPREHEND_LANGUAGE", "en")
MAX_COMPREHEND_BYTES = 5000  # Comprehend limit per text input

# Lazy-initialised clients (reused across warm invocations)
_comprehend_client = None
_firehose_client = None


def _get_comprehend():
    global _comprehend_client
    if _comprehend_client is None:
        _comprehend_client = boto3.client("comprehend")
    return _comprehend_client


def _get_firehose():
    global _firehose_client
    if _firehose_client is None:
        _firehose_client = boto3.client("firehose")
    return _firehose_client


def _truncate_text(text: str, max_bytes: int = MAX_COMPREHEND_BYTES) -> str:
    """Truncate text to fit within Comprehend's byte limit."""
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


def analyse_sentiment(text: str) -> dict[str, Any]:
    """
    Call Comprehend DetectSentiment and return a dict with sentiment label
    and per-class confidence scores.
    """
    comprehend = _get_comprehend()
    truncated = _truncate_text(text)
    try:
        response = comprehend.detect_sentiment(
            Text=truncated, LanguageCode=COMPREHEND_LANGUAGE
        )
    except ClientError as exc:
        logger.error("Comprehend DetectSentiment failed: %s", exc)
        return {
            "sentiment": "UNKNOWN",
            "confidence_positive": 0.0,
            "confidence_negative": 0.0,
            "confidence_neutral": 0.0,
            "confidence_mixed": 0.0,
        }

    scores = response.get("SentimentScore", {})
    return {
        "sentiment": response.get("Sentiment", "UNKNOWN"),
        "confidence_positive": round(scores.get("Positive", 0.0), 6),
        "confidence_negative": round(scores.get("Negative", 0.0), 6),
        "confidence_neutral": round(scores.get("Neutral", 0.0), 6),
        "confidence_mixed": round(scores.get("Mixed", 0.0), 6),
    }


def extract_entities(text: str) -> list[dict[str, Any]]:
    """
    Call Comprehend DetectEntities and return a list of entity dicts
    with text, type, and confidence score.
    """
    comprehend = _get_comprehend()
    truncated = _truncate_text(text)
    try:
        response = comprehend.detect_entities(
            Text=truncated, LanguageCode=COMPREHEND_LANGUAGE
        )
    except ClientError as exc:
        logger.error("Comprehend DetectEntities failed: %s", exc)
        return []

    entities: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for entity in response.get("Entities", []):
        key = (entity["Text"], entity["Type"])
        if key in seen:
            continue
        seen.add(key)
        entities.append(
            {
                "text": entity["Text"],
                "type": entity["Type"],
                "score": round(entity.get("Score", 0.0), 6),
            }
        )
    return entities


def _build_enriched_record(original: dict[str, Any]) -> dict[str, Any]:
    """Run NLP analysis and merge results into the original record."""
    text = original.get("text", "")
    if not text:
        logger.warning("Record %s has no text; skipping NLP.", original.get("record_id"))
        sentiment_result = {
            "sentiment": "UNKNOWN",
            "confidence_positive": 0.0,
            "confidence_negative": 0.0,
            "confidence_neutral": 0.0,
            "confidence_mixed": 0.0,
        }
        entities = []
    else:
        sentiment_result = analyse_sentiment(text)
        entities = extract_entities(text)

    enriched = {
        **original,
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "sentiment": sentiment_result["sentiment"],
        "confidence_positive": sentiment_result["confidence_positive"],
        "confidence_negative": sentiment_result["confidence_negative"],
        "confidence_neutral": sentiment_result["confidence_neutral"],
        "confidence_mixed": sentiment_result["confidence_mixed"],
        "entities": entities,
        "entity_count": len(entities),
    }

    # Add a date partition key (YYYY-MM-DD) for Athena
    try:
        ts = original.get("timestamp", "")
        enriched["date_partition"] = ts[:10] if ts else datetime.now(timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        enriched["date_partition"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    return enriched


def _send_to_firehose(records: list[dict[str, Any]]) -> None:
    """Send a batch of enriched records to Kinesis Firehose."""
    firehose = _get_firehose()
    firehose_records = []
    for record in records:
        # Each record is a newline-delimited JSON line
        data = json.dumps(record, default=str) + "\n"
        firehose_records.append({"Data": data.encode("utf-8")})

    # Firehose PutRecordBatch supports up to 500 records
    batch_size = 500
    for i in range(0, len(firehose_records), batch_size):
        batch = firehose_records[i : i + batch_size]
        try:
            response = firehose.put_record_batch(
                DeliveryStreamName=FIREHOSE_STREAM_NAME,
                Records=batch,
            )
            failed = response.get("FailedPutCount", 0)
            if failed > 0:
                logger.error(
                    "Firehose batch had %d failures out of %d records.",
                    failed,
                    len(batch),
                )
        except ClientError as exc:
            logger.error("Firehose put_record_batch failed: %s", exc)


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """
    AWS Lambda entry point. Processes Kinesis event records.

    Args:
        event: Kinesis event containing base64-encoded records.
        context: Lambda context object.

    Returns:
        Dict with processing summary.
    """
    kinesis_records = event.get("Records", [])
    logger.info("Received %d Kinesis records.", len(kinesis_records))

    enriched_records: list[dict[str, Any]] = []
    error_count = 0

    for kinesis_record in kinesis_records:
        try:
            # Decode the Kinesis record payload
            raw_data = kinesis_record["kinesis"]["data"]
            decoded = base64.b64decode(raw_data).decode("utf-8")
            original = json.loads(decoded)
        except (KeyError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            logger.error("Failed to decode record: %s", exc)
            error_count += 1
            continue

        try:
            enriched = _build_enriched_record(original)
            enriched_records.append(enriched)
        except Exception as exc:
            logger.error(
                "Failed to process record %s: %s",
                original.get("record_id", "unknown"),
                exc,
            )
            error_count += 1

    if enriched_records:
        _send_to_firehose(enriched_records)

    summary = {
        "total_received": len(kinesis_records),
        "successfully_processed": len(enriched_records),
        "errors": error_count,
    }
    logger.info("Processing complete: %s", summary)
    return summary
