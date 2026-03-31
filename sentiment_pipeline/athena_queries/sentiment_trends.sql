-- Sentiment trend over time (daily aggregation)
SELECT
    year || '-' || month || '-' || day AS date,
    sentiment,
    COUNT(*) AS record_count,
    AVG(sentiment_scores.positive) AS avg_positive,
    AVG(sentiment_scores.negative) AS avg_negative,
    AVG(sentiment_scores.neutral) AS avg_neutral
FROM sentiment_analytics.sentiment_records
GROUP BY year, month, day, sentiment
ORDER BY date DESC, sentiment
LIMIT 500;
