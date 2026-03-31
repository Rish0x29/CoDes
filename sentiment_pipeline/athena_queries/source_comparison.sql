-- Compare sentiment across different sources
SELECT
    source,
    COUNT(*) AS total_records,
    SUM(CASE WHEN sentiment = 'POSITIVE' THEN 1 ELSE 0 END) AS positive_count,
    SUM(CASE WHEN sentiment = 'NEGATIVE' THEN 1 ELSE 0 END) AS negative_count,
    SUM(CASE WHEN sentiment = 'NEUTRAL' THEN 1 ELSE 0 END) AS neutral_count,
    SUM(CASE WHEN sentiment = 'MIXED' THEN 1 ELSE 0 END) AS mixed_count,
    ROUND(AVG(sentiment_scores.positive), 4) AS avg_positive_score,
    ROUND(AVG(sentiment_scores.negative), 4) AS avg_negative_score,
    AVG(entity_count) AS avg_entities_per_record
FROM sentiment_analytics.sentiment_records
GROUP BY source
ORDER BY total_records DESC;
