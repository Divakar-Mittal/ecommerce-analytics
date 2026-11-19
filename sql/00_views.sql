-- Semantic layer: one place where business definitions live.
--   GMV          = value of all non-cancelled orders (before returns)
--   net revenue  = value of delivered orders only (returns and cancellations excluded)
--   gross profit = net revenue - cost of goods sold

DROP VIEW IF EXISTS v_order_lines;
CREATE VIEW v_order_lines AS
SELECT
    oi.order_item_id,
    o.order_id,
    o.customer_id,
    o.order_date,
    strftime('%Y-%m', o.order_date)                            AS order_month,
    o.status,
    o.discount_code,
    o.has_discount,
    p.product_id,
    p.product_name,
    p.category,
    c.region,
    c.acquisition_channel,
    c.age_band,
    oi.quantity,
    oi.unit_price,
    oi.line_total,
    oi.quantity * p.unit_cost                                  AS line_cost,
    CASE WHEN o.status <> 'cancelled' THEN oi.line_total ELSE 0 END AS gmv,
    CASE WHEN o.status = 'delivered' THEN oi.line_total ELSE 0 END  AS net_revenue,
    CASE WHEN o.status = 'delivered'
         THEN oi.line_total - oi.quantity * p.unit_cost ELSE 0 END AS gross_profit
FROM order_items oi
JOIN orders    o ON o.order_id    = oi.order_id
JOIN products  p ON p.product_id  = oi.product_id
JOIN customers c ON c.customer_id = o.customer_id;

DROP VIEW IF EXISTS v_orders;
CREATE VIEW v_orders AS
SELECT
    order_id,
    customer_id,
    order_date,
    order_month,
    status,
    has_discount,
    region,
    acquisition_channel,
    SUM(quantity)     AS units,
    SUM(gmv)          AS gmv,
    SUM(net_revenue)  AS net_revenue,
    SUM(gross_profit) AS gross_profit,
    ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY order_date, order_id) AS customer_order_number
FROM v_order_lines
GROUP BY order_id;
