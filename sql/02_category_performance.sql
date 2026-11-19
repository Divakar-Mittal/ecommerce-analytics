-- Category scorecard: revenue, profitability and returns.
WITH cat AS (
    SELECT
        category,
        SUM(CASE WHEN status <> 'cancelled' THEN quantity ELSE 0 END) AS units_sold,
        SUM(gmv)                                                     AS gmv,
        SUM(net_revenue)                                             AS net_revenue,
        SUM(gross_profit)                                            AS gross_profit,
        SUM(CASE WHEN status = 'returned' THEN line_total ELSE 0 END) AS returned_value
    FROM v_order_lines
    GROUP BY category
)
SELECT
    category,
    units_sold,
    ROUND(net_revenue, 2)                                  AS net_revenue,
    ROUND(net_revenue / SUM(net_revenue) OVER (), 4)       AS revenue_share,
    ROUND(gross_profit, 2)                                 AS gross_profit,
    ROUND(gross_profit / SUM(gross_profit) OVER (), 4)     AS profit_share,
    ROUND(gross_profit / NULLIF(net_revenue, 0), 4)        AS gross_margin,
    ROUND(returned_value / NULLIF(gmv, 0), 4)              AS return_rate_by_value,
    ROUND(returned_value, 2)                               AS returned_value
FROM cat
ORDER BY net_revenue DESC;
