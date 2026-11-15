import pytest

from pedidos.errors import UnsafeQueryError
from pedidos.sql_guard import validate_sql

VALID_QUERIES = [
    "SELECT SUM(ventas) FROM ventas_mes_pais WHERE pais = 'España' AND mes = '2025-03'",
    "select cliente, total_comprado from top_clientes",
    "SELECT * FROM pedidos LIMIT 5;",
    "SELECT * FROM main.pedidos",
    "WITH marzo AS (SELECT * FROM pedidos WHERE fecha LIKE '2025-03%') SELECT COUNT(*) FROM marzo",
    "SELECT p.producto, COUNT(*) FROM pedidos p JOIN top_clientes t ON t.cliente = p.cliente GROUP BY 1",
    "SELECT pais FROM pedidos UNION SELECT pais FROM ventas_mes_pais",
    "SELECT strftime('%Y', fecha) AS anio, ROUND(SUM(importe), 2) FROM pedidos GROUP BY anio",
    "SELECT * FROM pedidos WHERE pedido_id IN (SELECT pedido_id FROM pedidos WHERE importe > 500)",
    "SELECT * FROM pedidos -- trailing comment",
]


@pytest.mark.parametrize("sql", VALID_QUERIES)
def test_read_only_queries_on_allowed_tables_pass(sql):
    validate_sql(sql)


UNSAFE_QUERIES = {
    "delete": "DELETE FROM pedidos",
    "update": "UPDATE pedidos SET importe = 0",
    "insert": "INSERT INTO pedidos (pedido_id) VALUES ('X')",
    "drop": "DROP TABLE pedidos",
    "create": "CREATE TABLE copia AS SELECT * FROM pedidos",
    "multiple_statements": "SELECT 1; DROP TABLE pedidos",
    "read_then_write": "SELECT * FROM pedidos; DELETE FROM pedidos",
    "table_not_allowed": "SELECT * FROM clientes_secretos",
    "catalog_sqlite_master": "SELECT sql FROM sqlite_master",
    "catalog_sqlite_schema": "SELECT name FROM sqlite_schema",
    "table_hidden_in_cte": "WITH pedidos AS (SELECT * FROM clientes_secretos) SELECT * FROM pedidos",
    "table_in_subquery": "SELECT * FROM pedidos WHERE cliente IN (SELECT nombre FROM clientes_secretos)",
    "table_in_join": "SELECT * FROM pedidos JOIN clientes_secretos USING (cliente)",
    "attached_database": "SELECT * FROM otra.pedidos",
    "table_function_pragma": "SELECT * FROM pragma_table_info('pedidos')",
    "table_function_json": "SELECT * FROM json_each('[1, 2]')",
    "dangerous_function": "SELECT load_extension('/tmp/malicioso.so')",
    "attach": "ATTACH DATABASE '/tmp/x.db' AS x",
    "pragma": "PRAGMA writable_schema = ON",
    "transaction": "BEGIN",
    "vacuum_into": "VACUUM INTO '/tmp/copia.db'",
    "recursive_cte": "WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM n) SELECT COUNT(*) FROM n",
    "empty": "",
    "whitespace_only": "   ",
    "comment_only": "-- SELECT * FROM pedidos",
    "not_sql": "Lo siento, no puedo ayudarte con eso.",  # an LLM apology instead of SQL
}


@pytest.mark.parametrize("sql", UNSAFE_QUERIES.values(), ids=UNSAFE_QUERIES.keys())
def test_unsafe_or_invalid_queries_are_rejected(sql):
    with pytest.raises(UnsafeQueryError):
        validate_sql(sql)


def test_rejection_explains_which_table_is_not_allowed():
    with pytest.raises(UnsafeQueryError, match="clientes_secretos"):
        validate_sql("SELECT * FROM clientes_secretos")


def test_queries_over_the_length_limit_are_rejected():
    with pytest.raises(UnsafeQueryError, match="larga"):
        validate_sql("SELECT * FROM pedidos WHERE cliente = '" + "x" * 10_000 + "'")
