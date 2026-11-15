"""System prompt for the LLM: schema, real values from the data and business rules.

The template lives in prompts/sql_generation.txt, so it can be read and versioned on its own.
The model only sees the schema and catalog values (countries, statuses, products and the date
range), never customer rows.

Facts the model would otherwise have to reason about are computed here instead. For example,
which year "marzo" refers to: in a real-API check, the model added up March across every year
when it only had the rule.
"""

from importlib.resources import files
from pathlib import Path

from pedidos.db import run_query

SPANISH_MONTHS = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)  # fmt: skip


def build_system_prompt(db_path: Path) -> str:
    """Fills the prompt template with the values that actually exist in the database."""

    def distinct(column: str) -> str:
        rows = run_query(db_path, f"SELECT DISTINCT {column} FROM pedidos ORDER BY {column}").rows
        return ", ".join(row[0] for row in rows)

    ((min_date, max_date),) = run_query(db_path, "SELECT MIN(fecha), MAX(fecha) FROM pedidos").rows

    # Latest year-month with data for each calendar month, e.g. ("marzo", "2025-03")
    latest = dict(
        run_query(
            db_path, "SELECT strftime('%m', fecha), MAX(strftime('%Y-%m', fecha)) FROM pedidos GROUP BY 1"
        ).rows
    )
    month_years = [
        (name, latest[f"{number:02d}"])
        for number, name in enumerate(SPANISH_MONTHS, start=1)
        if f"{number:02d}" in latest
    ]
    # Example of a month without a year: June if there is data for it, otherwise the first month.
    example_name, example_month = next((pair for pair in month_years if pair[0] == "junio"), month_years[0])

    template = files("pedidos").joinpath("prompts", "sql_generation.txt").read_text(encoding="utf-8")
    return template.format(
        countries=distinct("pais"),
        statuses=distinct("estado"),
        products=distinct("producto"),
        min_date=min_date,
        max_date=max_date,
        month_years=", ".join(f"{name} → {year_month}" for name, year_month in month_years),
        example_month_name=example_name,
        example_month=example_month,
    )
