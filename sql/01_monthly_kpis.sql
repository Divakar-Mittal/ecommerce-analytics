-- Monthly business KPIs, split into new vs returning customers.
SELECT
    order_month,
    COUNT(*)                                                     AS orders,
    COUNT(DISTINCT customer_id)                                  AS active_customers,
    SUM(CASE WHEN customer_order_number = 1 THEN 1 ELSE 0 END)   AS new_customers,
    ROUND(SUM(gmv), 2)                                           AS gmv,
    ROUND(SUM(net_revenue), 2)                                   AS net_revenue,
    ROUND(SUM(gross_profit), 2)                                  AS gross_profit,
    ROUND(SUM(gross_profit) / NULLIF(SUM(net_revenue), 0), 4)    AS gross_margin,
    ROUND(SUM(net_revenue) / NULLIF(SUM(status = 'delivered'), 0), 2) AS aov,
    ROUND(SUM(CASE WHEN customer_order_number > 1 THEN net_revenue ELSE 0 END)
          / NULLIF(SUM(net_revenue), 0), 4)                      AS returning_revenue_share
FROM v_orders
GROUP BY order_month
ORDER BY order_month;
