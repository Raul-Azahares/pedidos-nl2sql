-- Sales by month and country.
-- Business decision: a sale is a completed order. Cancelled, returned and pending orders do not
-- count. Because the rule lives in the view, the LLM never has to decide what counts as a sale.
CREATE VIEW ventas_mes_pais AS
SELECT
    strftime('%Y-%m', fecha) AS mes,          -- 'YYYY-MM'
    pais,
    COUNT(*)                 AS num_pedidos,
    ROUND(SUM(importe), 2)   AS ventas        -- euros
FROM pedidos
WHERE estado = 'completado'
GROUP BY mes, pais
ORDER BY mes, pais;

-- The 10 customers who buy the most: highest total amount in completed orders.
-- The tie-break on the name makes the result deterministic.
CREATE VIEW top_clientes AS
SELECT
    cliente,
    COUNT(*)               AS num_pedidos,
    ROUND(SUM(importe), 2) AS total_comprado  -- euros
FROM pedidos
WHERE estado = 'completado'
GROUP BY cliente
ORDER BY total_comprado DESC, cliente
LIMIT 10;
