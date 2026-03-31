-- Top mentioned entities across all sources
SELECT
    entity.text AS entity_name,
    entity.type AS entity_type,
    COUNT(*) AS mention_count,
    AVG(CASE WHEN sentiment = 'POSITIVE' THEN 1
             WHEN sentiment = 'NEGATIVE' THEN -1
             ELSE 0 END) AS avg_sentiment_score
FROM sentiment_analytics.sentiment_records
CROSS JOIN UNNEST(entities) AS t(entity)
WHERE year = CAST(YEAR(CURRENT_DATE) AS VARCHAR)
GROUP BY entity.text, entity.type
ORDER BY mention_count DESC
LIMIT 50;
