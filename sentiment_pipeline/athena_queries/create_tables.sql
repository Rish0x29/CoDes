-- Create database
CREATE DATABASE IF NOT EXISTS sentiment_analytics;

-- Create main sentiment table (partitioned by year/month/day and source)
CREATE EXTERNAL TABLE IF NOT EXISTS sentiment_analytics.sentiment_records (
    text STRING,
    source STRING,
    url STRING,
    published_at STRING,
    category STRING,
    ingested_at STRING,
    sentiment STRING,
    sentiment_scores STRUCT<
        positive: DOUBLE,
        negative: DOUBLE,
        neutral: DOUBLE,
        mixed: DOUBLE
    >,
    entities ARRAY<STRUCT<
        text: STRING,
        type: STRING,
        score: DOUBLE
    >>,
    key_phrases ARRAY<STRUCT<
        text: STRING,
        score: DOUBLE
    >>,
    language STRING,
    entity_count INT,
    processed_at STRING
)
PARTITIONED BY (year STRING, month STRING, day STRING)
ROW FORMAT SERDE 'org.openx.data.jsonserde.JsonSerDe'
LOCATION 's3://sentiment-pipeline-data/curated/'
TBLPROPERTIES ('has_encrypted_data'='false');

-- Repair partitions
MSCK REPAIR TABLE sentiment_analytics.sentiment_records;
