"""Tests for the sentiment processor Lambda."""

import json
import base64
import pytest
import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from sentiment_pipeline.processor import process_record, handler


@pytest.fixture
def sample_record():
    return {
        "text": "Tech stocks surge as AI revolution accelerates",
        "source": "demo",
        "category": "technology",
        "url": "",
        "published_at": "2024-01-15T10:00:00Z",
        "ingested_at": "2024-01-15T10:01:00Z",
    }


@pytest.fixture
def kinesis_event():
    records = [
        {"text": "Great news for the market today", "source": "test"},
        {"text": "Terrible crash in stock prices", "source": "test"},
    ]
    return {
        "Records": [
            {
                "kinesis": {
                    "data": base64.b64encode(json.dumps(r).encode("utf-8")).decode("utf-8"),
                    "sequenceNumber": f"seq_{i}",
                    "partitionKey": f"key_{i}",
                },
                "eventSource": "aws:kinesis",
            }
            for i, r in enumerate(records)
        ]
    }


@patch("sentiment_pipeline.processor.comprehend")
def test_process_record_adds_sentiment(mock_comprehend, sample_record):
    mock_comprehend.detect_sentiment.return_value = {
        "Sentiment": "POSITIVE",
        "SentimentScore": {"Positive": 0.95, "Negative": 0.01, "Neutral": 0.03, "Mixed": 0.01},
    }
    mock_comprehend.detect_entities.return_value = {
        "Entities": [{"Text": "AI", "Type": "OTHER", "Score": 0.99}]
    }
    mock_comprehend.detect_key_phrases.return_value = {
        "KeyPhrases": [{"Text": "AI revolution", "Score": 0.95}]
    }
    mock_comprehend.detect_dominant_language.return_value = {
        "Languages": [{"LanguageCode": "en", "Score": 0.99}]
    }

    result = process_record(sample_record)

    assert result["sentiment"] == "POSITIVE"
    assert "sentiment_scores" in result
    assert result["sentiment_scores"]["positive"] == 0.95
    assert len(result["entities"]) == 1
    assert result["entities"][0]["text"] == "AI"
    assert result["language"] == "en"
    assert "processed_at" in result
    assert "year" in result


@patch("sentiment_pipeline.processor.send_to_firehose")
@patch("sentiment_pipeline.processor.comprehend")
def test_handler_processes_kinesis_records(mock_comprehend, mock_firehose, kinesis_event):
    mock_comprehend.detect_sentiment.return_value = {
        "Sentiment": "POSITIVE",
        "SentimentScore": {"Positive": 0.8, "Negative": 0.1, "Neutral": 0.05, "Mixed": 0.05},
    }
    mock_comprehend.detect_entities.return_value = {"Entities": []}
    mock_comprehend.detect_key_phrases.return_value = {"KeyPhrases": []}
    mock_comprehend.detect_dominant_language.return_value = {
        "Languages": [{"LanguageCode": "en", "Score": 0.99}]
    }

    result = handler(kinesis_event, None)

    assert result["processed"] == 2
    assert result["errors"] == 0
    mock_firehose.assert_called_once()


def test_process_record_empty_text():
    with patch("sentiment_pipeline.processor.comprehend") as mock_comp:
        mock_comp.detect_dominant_language.return_value = {"Languages": []}
        result = process_record({"text": ""})
        assert result["sentiment"] == "NEUTRAL"
