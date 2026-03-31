"""Tests for the sentiment data producer."""

import pytest
import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from sentiment_pipeline.producer import (
    KinesisProducer, fetch_demo_data, fetch_from_rss, DEMO_HEADLINES,
)


def test_demo_data_generation():
    records = list(fetch_demo_data())
    assert len(records) == len(DEMO_HEADLINES)
    for record in records:
        assert "text" in record
        assert "source" in record
        assert "category" in record
        assert "ingested_at" in record
        assert len(record["text"]) > 0


@patch("sentiment_pipeline.producer.boto3")
def test_kinesis_producer_put_record(mock_boto3):
    mock_client = MagicMock()
    mock_boto3.client.return_value = mock_client
    mock_client.put_record.return_value = {"ShardId": "shard-1", "SequenceNumber": "123"}

    producer = KinesisProducer("test-stream")
    result = producer.put_record({"text": "Test headline", "source": "test"})

    mock_client.put_record.assert_called_once()
    assert result["ShardId"] == "shard-1"


@patch("sentiment_pipeline.producer.boto3")
def test_kinesis_producer_batch(mock_boto3):
    mock_client = MagicMock()
    mock_boto3.client.return_value = mock_client
    mock_client.put_records.return_value = {"FailedRecordCount": 0, "Records": []}

    producer = KinesisProducer("test-stream")
    records = [{"text": f"Headline {i}", "source": "test"} for i in range(10)]
    results = producer.put_records_batch(records)

    assert len(results) == 1
    mock_client.put_records.assert_called_once()
