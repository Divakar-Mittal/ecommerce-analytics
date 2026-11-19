-- RFM segmentation (Recency, Frequency, Monetary), scored 1-5 with NTILE.
-- Snapshot date = day after the last order in the data.
WITH snapshot AS (
    SELECT date(MAX(order_date), '+1 day') AS snap FROM v_orders
),
base AS (
    SELECT
        customer_id,
        CAST(julianday((SELECT snap FROM snapshot)) - julianday(MAX(order_date)) AS INT) AS recency_days,
        COUNT(*)                     AS frequency,
        ROUND(SUM(net_revenue), 2)   AS monetary
    FROM v_orders
    WHERE status <> 'cancelled'
    GROUP BY customer_id
),
scored AS (
    SELECT
        *,
        6 - NTILE(5) OVER (ORDER BY recency_days)          AS r_score,  -- recent = 5
        -- most customers buy once, so frequency is bucketed by business rules not NTILE
        CASE WHEN frequency >= 5 THEN 5 WHEN frequency = 4 THEN 4
             WHEN frequency = 3 THEN 3 WHEN frequency = 2 THEN 2 ELSE 1 END AS f_score,
        NTILE(5) OVER (ORDER BY monetary)                  AS m_score
    FROM base
)
SELECT
    *,
    CASE
        WHEN r_score >= 4 AND f_score >= 3                  THEN 'Champions'
        WHEN r_score >= 3 AND f_score >= 2                  THEN 'Loyal'
        WHEN r_score >= 4 AND f_score = 1                   THEN 'New / Promising'
        WHEN r_score <= 2 AND f_score >= 2 AND m_score >= 3 THEN 'At Risk'
        WHEN r_score <= 2 AND f_score = 1                   THEN 'Hibernating'
        ELSE 'Needs Attention'
    END AS segment
FROM scored;
