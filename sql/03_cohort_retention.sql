-- Monthly acquisition cohorts: what share of each cohort orders again N months later.
WITH firsts AS (
    SELECT customer_id, MIN(order_month) AS cohort_month
    FROM v_orders
    WHERE status <> 'cancelled'
    GROUP BY customer_id
),
activity AS (
    SELECT DISTINCT
        f.cohort_month,
        o.customer_id,
        (CAST(substr(o.order_month, 1, 4) AS INT) - CAST(substr(f.cohort_month, 1, 4) AS INT)) * 12
      + (CAST(substr(o.order_month, 6, 2) AS INT) - CAST(substr(f.cohort_month, 6, 2) AS INT)) AS month_number
    FROM v_orders o
    JOIN firsts f USING (customer_id)
    WHERE o.status <> 'cancelled'
),
sizes AS (
    SELECT cohort_month, COUNT(*) AS cohort_size FROM firsts GROUP BY cohort_month
)
SELECT
    a.cohort_month,
    s.cohort_size,
    a.month_number,
    COUNT(*)                                     AS active_customers,
    ROUND(COUNT(*) * 1.0 / s.cohort_size, 4)     AS retention_rate
FROM activity a
JOIN sizes s USING (cohort_month)
GROUP BY a.cohort_month, a.month_number
ORDER BY a.cohort_month, a.month_number;
