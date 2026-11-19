-- Regional net revenue, 2024 vs 2025.
WITH r AS (
    SELECT
        region,
        SUM(CASE WHEN substr(order_month, 1, 4) = '2024' THEN net_revenue ELSE 0 END) AS revenue_2024,
        SUM(CASE WHEN substr(order_month, 1, 4) = '2025' THEN net_revenue ELSE 0 END) AS revenue_2025
    FROM v_orders
    GROUP BY region
)
SELECT
    region,
    ROUND(revenue_2024, 2) AS revenue_2024,
    ROUND(revenue_2025, 2) AS revenue_2025,
    ROUND((revenue_2025 - revenue_2024) / NULLIF(revenue_2024, 0), 4) AS yoy_growth
FROM r
ORDER BY revenue_2025 DESC;
