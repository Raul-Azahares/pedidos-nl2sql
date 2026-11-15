"""Second line of defense: SQLite itself rejects anything dangerous even if the validator failed.

These tests call run_query directly, without going through validate_sql.
"""

import sqlite3
from contextlib import closing

import pytest

from pedidos.db import run_query
from pedidos.errors import DatabaseUnavailableError, QueryTimeoutError, UnsafeQueryError


def test_allowed_query_returns_columns_and_rows(sample_db):
    result = run_query(sample_db, "SELECT cliente, total_comprado FROM top_clientes")
    assert result.columns == ["cliente", "total_comprado"]
    assert result.rows[0] == ("Marie Dubois", 300.0)
    assert result.truncated is False


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM pedidos",
        "UPDATE pedidos SET importe = 0",
        "INSERT INTO pedidos (pedido_id) VALUES ('X')",
        "DROP TABLE pedidos",
        "CREATE TABLE copia (x)",
        "SELECT sql FROM sqlite_master",
        "ATTACH DATABASE ':memory:' AS otra",
        "PRAGMA writable_schema = ON",
        "SELECT load_extension('/tmp/malicioso.so')",
        "WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM n) SELECT COUNT(*) FROM n",
    ],
)
def test_engine_rejects_dangerous_sql_without_the_validator(sample_db, sql):
    with pytest.raises(UnsafeQueryError):
        run_query(sample_db, sql)


def test_engine_rejects_tables_outside_the_allowlist(sample_db):
    with closing(sqlite3.connect(sample_db)) as conn, conn:
        conn.execute("CREATE TABLE secreta (dato TEXT)")
    with pytest.raises(UnsafeQueryError):
        run_query(sample_db, "SELECT * FROM secreta")


def test_database_is_unchanged_after_rejected_writes(sample_db):
    with pytest.raises(UnsafeQueryError):
        run_query(sample_db, "DELETE FROM pedidos")
    assert run_query(sample_db, "SELECT COUNT(*) FROM pedidos").rows == [(6,)]


def test_slow_queries_are_cancelled(sample_db):
    cross_join = ", ".join(f"pedidos t{i}" for i in range(9))  # 6^9 ≈ 10 million rows
    with pytest.raises(QueryTimeoutError):
        run_query(sample_db, f"SELECT COUNT(*) FROM {cross_join}", timeout_s=0.05)


def test_results_are_capped_and_flagged_as_truncated(sample_db):
    result = run_query(sample_db, "SELECT pedido_id FROM pedidos ORDER BY pedido_id", max_rows=2)
    assert result.rows == [("P1",), ("P2",)]
    assert result.truncated is True


def test_missing_database_gives_a_clear_error(tmp_path):
    with pytest.raises(DatabaseUnavailableError, match="make etl"):
        run_query(tmp_path / "no_existe.db", "SELECT 1")
