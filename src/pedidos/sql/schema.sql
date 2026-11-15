-- Clean orders. The constraints are the last quality barrier: if the cleaning step ever let an
-- invalid value through, the load would fail instead of storing it.
CREATE TABLE pedidos (
    pedido_id TEXT PRIMARY KEY,
    fecha     TEXT NOT NULL CHECK (fecha = date(fecha)),   -- ISO 8601 (YYYY-MM-DD) and a real date
    cliente   TEXT NOT NULL CHECK (length(trim(cliente)) > 0),
    pais      TEXT NOT NULL,
    producto  TEXT NOT NULL CHECK (length(trim(producto)) > 0),
    importe   REAL NOT NULL CHECK (importe > 0),           -- euros, two decimals
    estado    TEXT NOT NULL CHECK (estado IN ('completado', 'cancelado', 'pendiente', 'devuelto'))
) STRICT;
