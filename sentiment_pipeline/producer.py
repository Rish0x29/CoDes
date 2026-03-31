"""
Multi-Source Data Producer - Sends text records to Kinesis.
Supports: NewsAPI, RSS feeds, and demo/mock mode.
"""

import os
import json
import time
import logging
import hashlib
from datetime import datetime, timezone
from typing import Generator

import boto3
import requests

logger = logging.getLogger(__name__)

DEMO_HEADLINES = [
    {"text": "Tech stocks surge as AI revolution accelerates across industries", "source": "demo", "category": "technology"},
    {"text": "Federal Reserve holds interest rates steady amid inflation concerns", "source": "demo", "category": "finance"},
    {"text": "Major cybersecurity breach exposes millions of customer records", "source": "demo", "category": "security"},
    {"text": "New renewable energy plant opens, creating thousands of jobs", "source": "demo", "category": "energy"},
    {"text": "Healthcare startup raises $500M to revolutionize drug discovery with AI", "source": "demo", "category": "healthcare"},
    {"text": "Global chip shortage easing as new semiconductor fabs come online", "source": "demo", "category": "technology"},
    {"text": "Cryptocurrency market crashes following regulatory crackdown", "source": "demo", "category": "crypto"},
    {"text": "Electric vehicle sales hit record high in Q3 reports", "source": "demo", "category": "automotive"},
    {"text": "Major bank announces massive layoffs amid restructuring", "source": "demo", "category": "finance"},
    {"text": "Climate summit reaches historic agreement on carbon emissions", "source": "demo", "category": "environment"},
    {"text": "Social media platform faces backlash over privacy policy changes", "source": "demo", "category": "technology"},
    {"text": "Unemployment rate drops to lowest level in two decades", "source": "demo", "category": "economy"},
    {"text": "Cloud computing revenue exceeds expectations for major providers", "source": "demo", "category": "technology"},
    {"text": "Oil prices spike following supply disruption in Middle East", "source": "demo", "category": "energy"},
    {"text": "Retail giant reports disappointing earnings missing analyst estimates", "source": "demo", "category": "retail"},
]


class KinesisProducer:
    def __init__(self, stream_name: str, region: str = "us-east-1"):
        self.stream_name = stream_name
        self.kinesis = boto3.client("kinesis", region_name=region)

    def put_record(self, record: dict) -> dict:
        partition_key = hashlib.md5(record.get("text", "").encode()).hexdigest()[:8]
        response = self.kinesis.put_record(
            StreamName=self.stream_name,
            Data=json.dumps(record).encode("utf-8"),
            PartitionKey=partition_key,
        )
        return response

    def put_records_batch(self, records: list) -> dict:
        kinesis_records = []
        for record in records:
            partition_key = hashlib.md5(record.get("text", "").encode()).hexdigest()[:8]
            kinesis_records.append({
                "Data": json.dumps(record).encode("utf-8"),
                "PartitionKey": partition_key,
            })

        batch_size = 500
        results = []
        for i in range(0, len(kinesis_records), batch_size):
            batch = kinesis_records[i:i + batch_size]
            response = self.kinesis.put_records(StreamName=self.stream_name, Records=batch)
            results.append(response)
            failed = response.get("FailedRecordCount", 0)
            if failed > 0:
                logger.warning(f"Failed to put {failed} records in batch")

        return results


def fetch_from_newsapi(api_key: str, query: str = "technology OR finance OR AI",
                       page_size: int = 50) -> Generator[dict, None, None]:
    url = "https://newsapi.org/v2/everything"
    params = {"q": query, "pageSize": page_size, "sortBy": "publishedAt",
              "language": "en", "apiKey": api_key}
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()

    for article in data.get("articles", []):
        yield {
            "text": f"{article.get('title', '')}. {article.get('description', '')}",
            "source": article.get("source", {}).get("name", "newsapi"),
            "url": article.get("url", ""),
            "published_at": article.get("publishedAt", ""),
            "category": "news",
            "ingested_at": datetime.now(timezone.utc).isoformat(),
        }


def fetch_from_rss(feed_urls: list) -> Generator[dict, None, None]:
    import feedparser

    for feed_url in feed_urls:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:20]:
                yield {
                    "text": f"{entry.get('title', '')}. {entry.get('summary', '')[:500]}",
                    "source": feed.feed.get("title", feed_url),
                    "url": entry.get("link", ""),
                    "published_at": entry.get("published", ""),
                    "category": "rss",
                    "ingested_at": datetime.now(timezone.utc).isoformat(),
                }
        except Exception as e:
            logger.error(f"Error fetching RSS feed {feed_url}: {e}")


def fetch_demo_data() -> Generator[dict, None, None]:
    for headline in DEMO_HEADLINES:
        yield {
            "text": headline["text"],
            "source": headline["source"],
            "category": headline["category"],
            "url": "",
            "published_at": datetime.now(timezone.utc).isoformat(),
            "ingested_at": datetime.now(timezone.utc).isoformat(),
        }


def run_producer(stream_name: str, mode: str = "demo", region: str = "us-east-1",
                 newsapi_key: str = "", rss_feeds: list = None, interval_seconds: int = 5):
    producer = KinesisProducer(stream_name, region)
    logger.info(f"Starting producer in {mode} mode for stream {stream_name}")

    while True:
        records = []
        if mode == "demo":
            records = list(fetch_demo_data())
        elif mode == "newsapi":
            records = list(fetch_from_newsapi(newsapi_key))
        elif mode == "rss":
            records = list(fetch_from_rss(rss_feeds or []))
        elif mode == "all":
            records = list(fetch_demo_data())
            if newsapi_key:
                records.extend(fetch_from_newsapi(newsapi_key))
            if rss_feeds:
                records.extend(fetch_from_rss(rss_feeds))

        if records:
            logger.info(f"Sending {len(records)} records to Kinesis")
            producer.put_records_batch(records)

        time.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    stream = os.environ.get("KINESIS_STREAM", "sentiment-pipeline-stream")
    mode = os.environ.get("PRODUCER_MODE", "demo")
    run_producer(stream, mode=mode)
