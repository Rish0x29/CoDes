CREATE DATABASE IF NOT EXISTS churn_analytics;

CREATE EXTERNAL TABLE IF NOT EXISTS churn_analytics.customer_scores (
    customer_id STRING,
    churn_probability DOUBLE,
    risk_tier STRING,
    churn_score DOUBLE,
    top_risk_factors STRING,
    tenure INT,
    contract STRING,
    monthly_charges DOUBLE,
    internet_service STRING,
    satisfaction_score INT
)
ROW FORMAT SERDE 'org.apache.hadoop.hive.serde2.OpenCSVSerde'
LOCATION 's3://churn-curated/scores/'
TBLPROPERTIES ('skip.header.line.count'='1');
