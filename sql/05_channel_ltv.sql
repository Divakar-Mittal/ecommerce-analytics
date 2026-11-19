-- Acquisition channel quality: repeat rate and customer lifetime value (to date).
WITH per_customer AS (
    SELECT
        c.customer_id,
        c.acquisition_channel,
        COUNT(o.order_id)                AS orders,
        COALESCE(SUM(o.net_revenue), 0)  AS revenue,
        COALESCE(SUM(o.gross_profit), 0) AS profit
    FROM customers c
    JOIN v_orders o ON o.customer_id = c.customer_id AND o.status <> 'cancelled'
    GROUP BY c.customer_id
)
SELECT
    acquisition_channel,
    COUNT(*)                                          AS customers,
    ROUND(AVG(orders), 2)                             AS avg_orders_per_customer,
    ROUND(AVG(CASE WHEN orders >= 2 THEN 1.0 ELSE 0 END), 4) AS repeat_purchase_rate,
    ROUND(AVG(revenue), 2)                            AS avg_revenue_per_customer,
    ROUND(AVG(profit), 2)                             AS avg_profit_per_customer
FROM per_customer
GROUP BY acquisition_channel
ORDER BY avg_profit_per_customer DESC;
