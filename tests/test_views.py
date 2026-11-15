import sqlite3
from contextlib import closing
from datetime import date
from decimal import Decimal

from pedidos import etl
from pedidos.cleaning import CleaningResult, Order


def query(db_path, sql):
    with closing(sqlite3.connect(db_path)) as conn:
        return conn.execute(sql).fetchall()


def test_ventas_mes_pais_only_counts_completed_orders(sample_db):
    assert query(sample_db, "SELECT mes, pais, num_pedidos, ventas FROM ventas_mes_pais") == [
        ("2024-03", "España", 1, 70.0),
        ("2025-03", "España", 2, 300.0),  # the cancelled March order does not count
        ("2025-03", "Francia", 1, 300.0),
        ("2025-04", "España", 1, 40.0),
    ]


def test_top_clientes_ranks_by_total_spent(sample_db):
    assert query(sample_db, "SELECT cliente, num_pedidos, total_comprado FROM top_clientes") == [
        ("Marie Dubois", 1, 300.0),
        ("Luis Gil", 2, 240.0),
        ("Ana Ruiz", 2, 170.0),  # her cancelled order does not count
    ]


def test_top_clientes_returns_exactly_ten_customers(tmp_path):
    orders = [
        Order(f"P{i}", date(2025, 1, 1), f"Cliente {i:02d}", "España", "Tablet", Decimal(i + 1), "completado")
        for i in range(15)
    ]
    db_path = tmp_path / "pedidos.db"
    etl.load(CleaningResult(orders=orders), db_path)

    rows = query(db_path, "SELECT cliente FROM top_clientes")

    assert len(rows) == 10
    assert rows[0] == ("Cliente 14",)
