-- Churn by contract type
SELECT contract, risk_tier, COUNT(*) as customers,
    AVG(churn_probability) as avg_churn_prob
FROM churn_analytics.customer_scores
GROUP BY contract, risk_tier
ORDER BY contract, risk_tier;

-- High-risk customers needing intervention
SELECT customer_id, churn_probability, risk_tier, contract, monthly_charges, satisfaction_score
FROM churn_analytics.customer_scores
WHERE risk_tier = 'HIGH'
ORDER BY churn_probability DESC
LIMIT 100;

-- Risk distribution summary
SELECT risk_tier, COUNT(*) as count,
    ROUND(AVG(churn_probability), 4) as avg_prob,
    ROUND(AVG(monthly_charges), 2) as avg_charges
FROM churn_analytics.customer_scores
GROUP BY risk_tier;
