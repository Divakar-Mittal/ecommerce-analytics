-- Do discount codes pay off? Compare order value, margin and returns.
SELECT
    CASE WHEN o.has_discount THEN 'Discounted' ELSE 'Full price' END AS order_type,
    COUNT(*)                                                        AS orders,
    ROUND(SUM(o.status = 'delivered') * 1.0 / COUNT(*), 4)          AS delivered_rate,
    ROUND(SUM(o.status = 'returned')  * 1.0 / COUNT(*), 4)          AS return_rate,
    ROUND(SUM(o.net_revenue) / NULLIF(SUM(o.status = 'delivered'), 0), 2) AS aov,
    ROUND(SUM(o.gross_profit) / NULLIF(SUM(o.net_revenue), 0), 4)   AS gross_margin,
    ROUND(SUM(o.net_revenue), 2)                                    AS net_revenue
FROM v_orders o
GROUP BY order_type;
