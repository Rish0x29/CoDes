"""
Multi-source data producer that sends text records to AWS Kinesis.

Supports:
  - NewsAPI (requires NEWSAPI_KEY environment variable)
  - RSS feeds (configurable list of feed URLs)
  - Mock/demo mode with realistic sample data

Records are batched and sent using Kinesis PutRecords for throughput.
"""

import json
import logging
import os
import time
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

import boto3
import feedparser
import requests
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)

MAX_KINESIS_BATCH = 500
MAX_RECORD_SIZE_BYTES = 1_048_576  # 1 MiB per Kinesis record
DEFAULT_STREAM_NAME = "sentiment-input-stream"

MOCK_ARTICLES = [
    {
        "title": "Tech Giants Report Record Earnings",
        "text": (
            "Major technology companies exceeded analyst expectations this quarter, "
            "with combined revenues surpassing $500 billion. Investors reacted positively, "
            "sending share prices to all-time highs across the sector."
        ),
        "source": "mock",
        "category": "business",
    },
    {
        "title": "Global Climate Summit Ends in Disappointment",
        "text": (
            "World leaders failed to reach a binding agreement on carbon emission targets "
            "at the annual climate summit. Environmental groups expressed frustration, "
            "calling the outcome a missed opportunity for meaningful action."
        ),
        "source": "mock",
        "category": "politics",
    },
    {
        "title": "New Study Reveals Benefits of Mediterranean Diet",
        "text": (
            "Researchers at a leading university published findings showing that adherence "
            "to a Mediterranean diet reduces the risk of heart disease by 30 percent. "
            "The study followed 12,000 participants over a decade."
        ),
        "source": "mock",
        "category": "health",
    },
    {
        "title": "Local Team Wins Championship in Dramatic Fashion",
        "text": (
            "In a thrilling overtime finish, the home team secured the national championship "
            "with a last-second goal. Fans erupted in celebration as the underdog squad "
            "completed one of the greatest comebacks in tournament history."
        ),
        "source": "mock",
        "category": "sports",
    },
    {
        "title": "Cybersecurity Breach Exposes Millions of Records",
        "text": (
            "A major data breach at a financial services firm has compromised the personal "
            "information of over 10 million customers. The company faces regulatory scrutiny "
            "and potential class-action lawsuits as investigators assess the damage."
        ),
        "source": "mock",
        "category": "technology",
    },
    {
        "title": "Space Agency Announces Mars Mission Timeline",
        "text": (
            "The national space agency unveiled a detailed roadmap for sending astronauts "
            "to Mars by 2038. The ambitious plan includes a series of preparatory missions "
            "and construction of an orbital staging platform."
        ),
        "source": "mock",
        "category": "science",
    },
    {
        "title": "Housing Market Shows Signs of Cooling",
        "text": (
            "After two years of rapid price increases, the housing market is beginning to "
            "stabilize. Mortgage rates have risen sharply, dampening buyer enthusiasm and "
            "leading to a modest decline in home sales nationwide."
        ),
        "source": "mock",
        "category": "business",
    },
    {
        "title": "Controversial Film Sparks Heated Debate",
        "text": (
            "A newly released documentary has ignited passionate discussion about freedom "
            "of expression and media responsibility. Critics are divided, with some praising "
            "the film's bold approach while others condemn its sensationalism."
        ),
        "source": "mock",
        "category": "entertainment",
    },
    {
        "title": "Breakthrough in Quantum Computing Announced",
        "text": (
            "Scientists have achieved a significant milestone in quantum computing, "
            "demonstrating a processor that can solve certain problems exponentially faster "
            "than classical supercomputers. The advance could revolutionize cryptography "
            "and drug discovery."
        ),
        "source": "mock",
        "category": "technology",
    },
    {
        "title": "Severe Weather Warnings Issued for Coastal Regions",
        "text": (
            "Meteorologists have issued urgent warnings as a powerful storm system approaches "
            "the eastern seaboard. Residents in low-lying areas are being urged to evacuate "
            "as flooding and destructive winds are expected over the next 48 hours."
        ),
        "source": "mock",
        "category": "weather",
    },
]

DEFAULT_RSS_FEEDS = [
    "https://feeds.bbci.co.uk/news/rss.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",
    "https://feeds.reuters.com/reuters/topNews",
]


def _build_record(title: str, text: str, source: str, category: str = "general") -> dict[str, Any]:
    """Build a standardised record dict ready for Kinesis."""
    return {
        "record_id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "category": category,
        "title": title,
        "text": text,
    }


def _truncate_to_kinesis_limit(payload_bytes: bytes) -> bytes:
    """Ensure a single record does not exceed the Kinesis size limit."""
    if len(payload_bytes) <= MAX_RECORD_SIZE_BYTES:
        return payload_bytes
    logger.warning("Record exceeds 1 MiB limit; truncating text field.")
    record = json.loads(payload_bytes)
    while len(json.dumps(record).encode("utf-8")) > MAX_RECORD_SIZE_BYTES:
        record["text"] = record["text"][: len(record["text"]) // 2]
    return json.dumps(record).encode("utf-8")


class BaseSource(ABC):
    """Abstract base class for data sources."""

    @abstractmethod
    def fetch(self) -> list[dict[str, Any]]:
        """Return a list of record dicts."""


class MockSource(BaseSource):
    """Generates sample records for demo / local testing."""

    def __init__(self, count: int = 10) -> None:
        self.count = count

    def fetch(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for i in range(self.count):
            article = MOCK_ARTICLES[i % len(MOCK_ARTICLES)]
            records.append(
                _build_record(
                    title=article["title"],
                    text=article["text"],
                    source=article["source"],
                    category=article["category"],
                )
            )
        logger.info("MockSource generated %d records.", len(records))
        return records


class NewsAPISource(BaseSource):
    """Fetches top headlines from NewsAPI (https://newsapi.org)."""

    BASE_URL = "https://newsapi.org/v2/top-headlines"

    def __init__(
        self,
        api_key: str | None = None,
        country: str = "us",
        page_size: int = 50,
    ) -> None:
        self.api_key = api_key or os.environ.get("NEWSAPI_KEY", "")
        if not self.api_key:
            raise ValueError(
                "NewsAPI key is required. Set NEWSAPI_KEY env var or pass api_key."
            )
        self.country = country
        self.page_size = min(page_size, 100)

    def fetch(self) -> list[dict[str, Any]]:
        params = {
            "apiKey": self.api_key,
            "country": self.country,
            "pageSize": self.page_size,
        }
        try:
            resp = requests.get(self.BASE_URL, params=params, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.error("NewsAPI request failed: %s", exc)
            return []

        data = resp.json()
        if data.get("status") != "ok":
            logger.error("NewsAPI error: %s", data.get("message", "unknown"))
            return []

        records: list[dict[str, Any]] = []
        for article in data.get("articles", []):
            title = article.get("title") or ""
            description = article.get("description") or ""
            content = article.get("content") or ""
            text = f"{description} {content}".strip()
            if not text:
                continue
            source_name = (article.get("source") or {}).get("name", "newsapi")
            records.append(
                _build_record(
                    title=title,
                    text=text,
                    source=f"newsapi:{source_name}",
                    category="news",
                )
            )
        logger.info("NewsAPISource fetched %d records.", len(records))
        return records


class RSSSource(BaseSource):
    """Fetches articles from a list of RSS feed URLs."""

    def __init__(self, feed_urls: list[str] | None = None) -> None:
        self.feed_urls = feed_urls or DEFAULT_RSS_FEEDS

    def fetch(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for url in self.feed_urls:
            try:
                feed = feedparser.parse(url)
            except Exception as exc:
                logger.error("Failed to parse RSS feed %s: %s", url, exc)
                continue

            feed_title = feed.feed.get("title", url)
            for entry in feed.entries:
                title = entry.get("title", "")
                summary = entry.get("summary", "")
                if not summary:
                    continue
                records.append(
                    _build_record(
                        title=title,
                        text=summary,
                        source=f"rss:{feed_title}",
                        category="news",
                    )
                )
        logger.info("RSSSource fetched %d records from %d feeds.", len(records), len(self.feed_urls))
        return records


class KinesisProducer:
    """Sends records to an AWS Kinesis Data Stream in batches."""

    def __init__(
        self,
        stream_name: str = DEFAULT_STREAM_NAME,
        region: str | None = None,
        kinesis_client: Any | None = None,
    ) -> None:
        self.stream_name = stream_name
        self.client = kinesis_client or boto3.client(
            "kinesis", region_name=region or os.environ.get("AWS_REGION", "us-east-1")
        )

    def send(self, records: list[dict[str, Any]]) -> dict[str, int]:
        """Send records to Kinesis in batches. Returns counts of success/failure."""
        if not records:
            logger.warning("No records to send.")
            return {"success": 0, "failure": 0}

        success_count = 0
        failure_count = 0

        for batch_start in range(0, len(records), MAX_KINESIS_BATCH):
            batch = records[batch_start : batch_start + MAX_KINESIS_BATCH]
            kinesis_records = []
            for record in batch:
                payload = json.dumps(record, default=str).encode("utf-8")
                payload = _truncate_to_kinesis_limit(payload)
                kinesis_records.append(
                    {
                        "Data": payload,
                        "PartitionKey": record.get("source", "default"),
                    }
                )

            retries = 0
            max_retries = 3
            to_send = kinesis_records

            while to_send and retries <= max_retries:
                try:
                    response = self.client.put_records(
                        StreamName=self.stream_name,
                        Records=to_send,
                    )
                except ClientError as exc:
                    logger.error("Kinesis PutRecords failed: %s", exc)
                    failure_count += len(to_send)
                    break

                failed = response.get("FailedRecordCount", 0)
                succeeded = len(to_send) - failed
                success_count += succeeded

                if failed == 0:
                    break

                # Collect failed records for retry
                retry_records = []
                for idx, result in enumerate(response.get("Records", [])):
                    if result.get("ErrorCode"):
                        retry_records.append(to_send[idx])

                to_send = retry_records
                retries += 1
                if to_send:
                    backoff = min(2**retries, 8)
                    logger.warning(
                        "Retrying %d failed records (attempt %d) after %ds backoff.",
                        len(to_send),
                        retries,
                        backoff,
                    )
                    time.sleep(backoff)

            if to_send and retries > max_retries:
                failure_count += len(to_send)
                logger.error(
                    "Gave up on %d records after %d retries.", len(to_send), max_retries
                )

        logger.info(
            "Kinesis send complete: %d succeeded, %d failed.", success_count, failure_count
        )
        return {"success": success_count, "failure": failure_count}


def run_pipeline(
    sources: list[str] | None = None,
    stream_name: str = DEFAULT_STREAM_NAME,
    region: str | None = None,
    interval_seconds: int = 0,
    mock_count: int = 10,
    rss_feeds: list[str] | None = None,
    newsapi_key: str | None = None,
) -> None:
    """
    Main entry point: fetch from the requested sources and push to Kinesis.

    Args:
        sources: list of source types to use ("mock", "newsapi", "rss").
                 Defaults to ["mock"].
        stream_name: Kinesis stream name.
        region: AWS region.
        interval_seconds: If > 0, repeat on this interval. 0 means run once.
        mock_count: Number of mock records per cycle.
        rss_feeds: Custom RSS feed URLs.
        newsapi_key: NewsAPI key override.
    """
    sources = sources or ["mock"]
    producer = KinesisProducer(stream_name=stream_name, region=region)

    source_objects: list[BaseSource] = []
    for src in sources:
        if src == "mock":
            source_objects.append(MockSource(count=mock_count))
        elif src == "newsapi":
            source_objects.append(NewsAPISource(api_key=newsapi_key))
        elif src == "rss":
            source_objects.append(RSSSource(feed_urls=rss_feeds))
        else:
            logger.warning("Unknown source type '%s'; skipping.", src)

    if not source_objects:
        logger.error("No valid sources configured. Exiting.")
        return

    while True:
        all_records: list[dict[str, Any]] = []
        for source in source_objects:
            try:
                all_records.extend(source.fetch())
            except Exception as exc:
                logger.error("Source %s failed: %s", type(source).__name__, exc)

        if all_records:
            result = producer.send(all_records)
            logger.info("Cycle result: %s", result)
        else:
            logger.info("No records fetched this cycle.")

        if interval_seconds <= 0:
            break
        logger.info("Sleeping %d seconds before next cycle.", interval_seconds)
        time.sleep(interval_seconds)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Sentiment Pipeline Producer")
    parser.add_argument(
        "--sources",
        nargs="+",
        default=["mock"],
        choices=["mock", "newsapi", "rss"],
        help="Data sources to use.",
    )
    parser.add_argument("--stream", default=DEFAULT_STREAM_NAME, help="Kinesis stream name.")
    parser.add_argument("--region", default=None, help="AWS region.")
    parser.add_argument("--interval", type=int, default=0, help="Repeat interval in seconds (0=once).")
    parser.add_argument("--mock-count", type=int, default=10, help="Number of mock records per cycle.")
    parser.add_argument("--rss-feeds", nargs="*", default=None, help="Custom RSS feed URLs.")
    parser.add_argument("--newsapi-key", default=None, help="NewsAPI key.")
    args = parser.parse_args()

    run_pipeline(
        sources=args.sources,
        stream_name=args.stream,
        region=args.region,
        interval_seconds=args.interval,
        mock_count=args.mock_count,
        rss_feeds=args.rss_feeds,
        newsapi_key=args.newsapi_key,
    )
