# Real-Time Sentiment Analysis Pipeline

Streaming NLP pipeline that ingests text data, analyzes sentiment with AWS Comprehend, and visualizes trends.

## Architecture

- **Kinesis Data Stream**: Ingests text records from multiple sources
- **Lambda**: Processes records with Comprehend (sentiment, entities, key phrases)
- **Kinesis Firehose**: Delivers enriched data to S3
- **S3**: Stores Parquet data partitioned by date
- **Glue Crawler**: Catalogs data for Athena
- **Athena**: SQL queries on sentiment data

## Data Sources

- **NewsAPI**: Real-time news headlines
- **RSS Feeds**: Configurable RSS feed ingestion
- **Demo Mode**: 15 built-in sample headlines for testing

## Setup

1. `pip install -r requirements.txt`
2. Deploy: `sam build && sam deploy --guided`
3. Start producer: `python -m sentiment_pipeline.producer`

## Testing

```bash
pytest sentiment_pipeline/tests/ -v
```
