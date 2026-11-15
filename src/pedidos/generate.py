"""Generates an orders CSV with intentional errors, to exercise the cleaning step.

Errors injected at fixed rates:
- duplicates of the same order: some exact, others reformatted with extra spaces or uppercase;
- dates in alternative formats (recoverable) and impossible or garbage dates;
- empty amounts, and amounts with a decimal comma;
- countries and statuses written in several ways.

The same seed always produces the same file.

Usage: python -m pedidos.generate [--orders 1200] [--seed 42] [--output data/raw/pedidos.csv]
"""

from __future__ import annotations

import argparse
import csv
import random
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

from pedidos.domain import CSV_COLUMNS

DEFAULT_OUTPUT = Path("data/raw/pedidos.csv")

START_DATE = date(2024, 1, 1)
END_DATE = date(2025, 12, 31)
N_CUSTOMERS = 150

PRODUCT_PRICES = {
    "Portátil": 899.00,
    "Escritorio elevable": 399.00,
    "Tablet": 329.00,
    "Monitor 27 pulgadas": 249.00,
    "Silla ergonómica": 229.00,
    "Impresora": 149.00,
    "Disco SSD 1 TB": 99.00,
    "Teclado mecánico": 89.00,
    "Auriculares": 59.00,
    "Webcam HD": 49.00,
    "Ratón inalámbrico": 29.00,
    "Memoria USB 64 GB": 12.00,
}
FIRST_NAMES = (
    "Lucía", "Hugo", "Martina", "Mateo", "Sofía", "Leo", "María", "Daniel", "Julia", "Pablo",
    "Paula", "Álvaro", "Valeria", "Manuel", "Emma", "Adrián", "Carmen", "Diego", "Elena", "Javier",
    "Sara", "Carlos", "Laura", "Marcos", "Irene",
)  # fmt: skip
LAST_NAMES = (
    "García", "Rodríguez", "González", "Fernández", "López", "Martínez", "Sánchez", "Pérez",
    "Gómez", "Martín", "Jiménez", "Ruiz", "Hernández", "Díaz", "Moreno", "Muñoz", "Álvarez",
    "Romero", "Navarro", "Torres",
)  # fmt: skip

# Weights aligned with pedidos.domain.COUNTRIES and pedidos.domain.STATUSES
COUNTRY_WEIGHTS = {
    "España": 40,
    "México": 18,
    "Francia": 12,
    "Alemania": 12,
    "Italia": 10,
    "Portugal": 8,
}
STATUS_WEIGHTS = {"completado": 75, "cancelado": 10, "pendiente": 8, "devuelto": 7}

# Error rates, as a fraction of the number of orders
DUPLICATE_RATE = 0.03
ALT_DATE_RATE = 0.05
BAD_DATE_RATE = 0.02
EMPTY_AMOUNT_RATE = 0.03
COMMA_AMOUNT_RATE = 0.04
COUNTRY_VARIANT_RATE = 0.06
STATUS_VARIANT_RATE = 0.04

ALT_DATE_FORMATS = ("%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y")
BAD_DATES = ("2025-02-30", "2024-13-05", "31/04/2025", "N/A", "", "ayer")
COUNTRY_VARIANTS = {
    "España": ("españa", " ESPAÑA", "Espana", "ES"),
    "México": ("mexico", "MÉXICO ", "Mexico", "MX"),
    "Francia": ("francia", "FRANCIA", "FR"),
    "Alemania": ("alemania", " Alemania ", "DE"),
    "Italia": ("italia", "ITALIA", "IT"),
    "Portugal": ("portugal", "PORTUGAL ", "PT"),
}
STATUS_VARIANTS = (str.capitalize, str.upper, lambda status: f" {status} ")


def generate_orders(n_orders: int, rng: random.Random) -> list[dict[str, str]]:
    """Clean orders sorted by date. A few customers concentrate many of the purchases."""
    names = rng.sample([f"{first} {last}" for first in FIRST_NAMES for last in LAST_NAMES], N_CUSTOMERS)
    countries = rng.choices(list(COUNTRY_WEIGHTS), list(COUNTRY_WEIGHTS.values()), k=N_CUSTOMERS)
    customers = list(zip(names, countries, strict=True))  # each customer lives in a single country
    # Weight ∝ 1/√rank: the top customer buys ~12 times more often than the bottom one
    customer_weights = [rank**-0.5 for rank in range(1, N_CUSTOMERS + 1)]

    span = (END_DATE - START_DATE).days
    dates = sorted(START_DATE + timedelta(days=rng.randint(0, span)) for _ in range(n_orders))

    orders = []
    for number, order_date in enumerate(dates, start=1):
        customer, country = rng.choices(customers, customer_weights)[0]
        product = rng.choice(list(PRODUCT_PRICES))
        quantity = rng.choices((1, 2, 3), (70, 20, 10))[0]
        discount = rng.choice((0, 0, 0, 0.05, 0.10, 0.15))
        amount = round(PRODUCT_PRICES[product] * quantity * (1 - discount), 2)
        status = rng.choices(list(STATUS_WEIGHTS), list(STATUS_WEIGHTS.values()))[0]
        orders.append(
            {
                "pedido_id": f"P{number:05d}",
                "fecha": order_date.isoformat(),
                "cliente": customer,
                "pais": country,
                "producto": product,
                "importe": f"{amount:.2f}",
                "estado": status,
            }
        )
    return orders


def inject_errors(
    orders: list[dict[str, str]], rng: random.Random
) -> tuple[list[dict[str, str]], Counter[str]]:
    """Returns a copy of the orders with intentional errors, plus a count of each error type."""
    rows = [dict(order) for order in orders]
    n = len(rows)
    stats: Counter[str] = Counter()

    def pick(*rates: float) -> list[list[int]]:
        """Disjoint groups of rows: a row never gets two errors in the same field."""
        sizes = [round(n * rate) for rate in rates]
        chosen = rng.sample(range(n), sum(sizes))
        groups, start = [], 0
        for size in sizes:
            groups.append(chosen[start : start + size])
            start += size
        return groups

    alt_dates, bad_dates = pick(ALT_DATE_RATE, BAD_DATE_RATE)
    for i in alt_dates:
        parsed = date.fromisoformat(rows[i]["fecha"])
        rows[i]["fecha"] = parsed.strftime(rng.choice(ALT_DATE_FORMATS))
    for i in bad_dates:
        rows[i]["fecha"] = rng.choice(BAD_DATES)
    stats["alternative_date_format"] = len(alt_dates)
    stats["invalid_date"] = len(bad_dates)

    empty_amounts, comma_amounts = pick(EMPTY_AMOUNT_RATE, COMMA_AMOUNT_RATE)
    for i in empty_amounts:
        rows[i]["importe"] = rng.choice(("", "  "))
    for i in comma_amounts:
        rows[i]["importe"] = rows[i]["importe"].replace(".", ",")
    stats["empty_amount"] = len(empty_amounts)
    stats["decimal_comma_amount"] = len(comma_amounts)

    (country_rows,) = pick(COUNTRY_VARIANT_RATE)
    for i in country_rows:
        rows[i]["pais"] = rng.choice(COUNTRY_VARIANTS[rows[i]["pais"]])
    stats["country_variant"] = len(country_rows)

    (status_rows,) = pick(STATUS_VARIANT_RATE)
    for i in status_rows:
        rows[i]["estado"] = rng.choice(STATUS_VARIANTS)(rows[i]["estado"])
    stats["status_variant"] = len(status_rows)

    # Duplicates are created last, so some copies also inherit the errors injected above.
    (duplicate_sources,) = pick(DUPLICATE_RATE)
    copies = []
    for i in duplicate_sources:
        copy = dict(rows[i])
        if rng.random() < 0.5:  # same order, different formatting
            copy["cliente"] = "  ".join(copy["cliente"].split()) + " "
            copy["pais"] = copy["pais"].upper()
            stats["reformatted_duplicate"] += 1
        else:
            stats["exact_duplicate"] += 1
        copies.append(copy)
    for copy in copies:
        rows.insert(rng.randint(0, len(rows)), copy)
    return rows, stats


def write_csv(rows: list[dict[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Generates the orders CSV with intentional errors.")
    parser.add_argument("--orders", type=int, default=1200, help="number of distinct orders")
    parser.add_argument("--seed", type=int, default=42, help="random generator seed")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="output CSV path")
    args = parser.parse_args(argv)

    rng = random.Random(args.seed)
    rows, stats = inject_errors(generate_orders(args.orders, rng), rng)
    write_csv(rows, args.output)

    print(f"{len(rows)} rows written to {args.output} ({args.orders} orders + duplicates)")
    for kind, count in sorted(stats.items()):
        print(f"  {kind:<28}{count:>5}")


if __name__ == "__main__":
    main()
