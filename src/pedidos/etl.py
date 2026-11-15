"""ETL: reads the dirty CSV, cleans it and loads it into SQLite.

Usage: python -m pedidos.etl [--input data/raw/pedidos.csv] [--db data/pedidos.db]
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from contextlib import closing
from importlib.resources import files
from pathlib import Path

from pedidos.cleaning import CleaningResult, clean_orders, format_report
from pedidos.config import Settings
from pedidos.domain import CSV_COLUMNS

DEFAULT_INPUT = Path("data/raw/pedidos.csv")
REJECTED_OUTPUT = Path("data/processed/rechazados.csv")
SQL_SCRIPTS = ("schema.sql",)


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = set(CSV_COLUMNS) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"The CSV is missing columns: {', '.join(sorted(missing))}")
        return list(reader)


def write_rejected(rejected: list[dict[str, str]], path: Path) -> None:
    """Rejected rows are kept outside the database, with their reason, so they can be reviewed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=[*CSV_COLUMNS, "motivo"], lineterminator="\n", extrasaction="ignore"
        )
        writer.writeheader()
        writer.writerows(rejected)


def load(result: CleaningResult, db_path: Path) -> None:
    """Builds the database from scratch in a temporary file and swaps it in atomically.

    The ETL can be rerun as many times as needed, and readers never see a half-finished load.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = db_path.with_name(db_path.name + ".tmp")
    tmp_path.unlink(missing_ok=True)
    with closing(sqlite3.connect(tmp_path)) as conn:
        for script in SQL_SCRIPTS:
            conn.executescript(files("pedidos").joinpath("sql", script).read_text(encoding="utf-8"))
        with conn:  # a single transaction for the whole load
            conn.executemany(
                "INSERT INTO pedidos (pedido_id, fecha, cliente, pais, producto, importe, estado)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        o.pedido_id,
                        o.fecha.isoformat(),
                        o.cliente,
                        o.pais,
                        o.producto,
                        float(o.importe),
                        o.estado,
                    )
                    for o in result.orders
                ],
            )
    tmp_path.replace(db_path)


def run(input_path: Path, db_path: Path, rejected_path: Path = REJECTED_OUTPUT) -> CleaningResult:
    result = clean_orders(read_rows(input_path))
    write_rejected(result.rejected, rejected_path)
    load(result, db_path)
    return result


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Cleans the orders CSV and loads it into SQLite.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="dirty orders CSV")
    parser.add_argument("--db", type=Path, default=Settings().db_path, help="output SQLite file")
    args = parser.parse_args(argv)

    if not args.input.exists():
        sys.exit(f"{args.input} does not exist. Generate the data first with: make data")
    result = run(args.input, args.db)
    print(format_report(result))
    print(f"\nDatabase: {args.db} · rejected rows: {REJECTED_OUTPUT}")


if __name__ == "__main__":
    main()
