import sqlite3
from contextlib import closing
from importlib.resources import files

import pytest

from pedidos import etl, generate


def write_csv(path, rows):
    base = {
        "pedido_id": "P00001",
        "fecha": "2025-03-15",
        "cliente": "Ana Ruiz",
        "pais": "España",
        "producto": "Tablet",
        "importe": "329.00",
        "estado": "completado",
    }
    generate.write_csv([base | r for r in rows], path)


def test_etl_loads_clean_rows_and_can_be_rerun(tmp_path):
    csv_path = tmp_path / "pedidos.csv"
    write_csv(csv_path, [{}, {"pedido_id": "P00002", "importe": ""}, {"fecha": "15/03/2025"}])
    db_path = tmp_path / "pedidos.db"

    for _ in range(2):  # rerunning the ETL does not duplicate data
        result = etl.run(csv_path, db_path, rejected_path=tmp_path / "rechazados.csv")

    with closing(sqlite3.connect(db_path)) as conn:
        loaded = conn.execute("SELECT pedido_id, fecha, importe FROM pedidos").fetchall()
    assert loaded == [("P00001", "2025-03-15", 329.0)]
    assert result.duplicates == 1
    assert (tmp_path / "rechazados.csv").read_text(encoding="utf-8").count("importe_vacio") == 1


def test_schema_is_the_last_barrier_against_invalid_data():
    with closing(sqlite3.connect(":memory:")) as conn:
        conn.executescript(files("pedidos").joinpath("sql", "schema.sql").read_text(encoding="utf-8"))
        with pytest.raises(sqlite3.IntegrityError):  # February 30th does not exist
            conn.execute(
                "INSERT INTO pedidos VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("P1", "2025-02-30", "Ana", "España", "Tablet", 10.0, "completado"),
            )
