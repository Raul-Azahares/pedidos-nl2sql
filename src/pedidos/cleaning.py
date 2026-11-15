"""Cleaning rules for the orders.

They are pure functions (no file reads or writes), so each rule can be tested on its own.
Order: normalize text -> parse -> validate -> deduplicate.
"""

from __future__ import annotations

import unicodedata
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from pedidos.domain import COUNTRIES, CSV_COLUMNS, STATUSES

# Accepted date formats, in order. An ambiguous date such as 03/04/2025 is read as day/month,
# which is the convention in every country we sell to.
DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y")
CENT = Decimal("0.01")


def comparison_key(text: str) -> str:
    """Key for comparing text: no surrounding spaces, lowercase and without accents."""
    decomposed = unicodedata.normalize("NFKD", text.strip().casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


COUNTRY_ALIASES = {comparison_key(country): country for country in COUNTRIES} | {
    "es": "España",
    "spain": "España",
    "mx": "México",
    "fr": "Francia",
    "france": "Francia",
    "de": "Alemania",
    "germany": "Alemania",
    "it": "Italia",
    "italy": "Italia",
    "pt": "Portugal",
}


def normalize_text(raw: str) -> str:
    """Strips surrounding spaces and collapses inner ones: ' Ana  Ruiz ' -> 'Ana Ruiz'."""
    return " ".join(raw.split())


def parse_date(raw: str) -> date | None:
    """Date in one of the accepted formats. None if it is empty, garbage or does not exist."""
    text = raw.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def parse_amount(raw: str) -> Decimal | None:
    """Positive amount rounded to cents (half up). Accepts a decimal comma.

    None if it is empty, not a number or not positive. Thousands separators are not supported.
    """
    try:
        amount = Decimal(raw.strip().replace(",", "."))
        if not amount.is_finite() or amount <= 0:
            return None
        return amount.quantize(CENT, rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return None


def normalize_country(raw: str) -> str | None:
    """Canonical country name ('ES', ' ESPAÑA', 'Espana' -> 'España'). None if it is unknown."""
    return COUNTRY_ALIASES.get(comparison_key(raw))


def normalize_status(raw: str) -> str | None:
    status = raw.strip().casefold()
    return status if status in STATUSES else None


@dataclass(frozen=True)
class Order:
    pedido_id: str
    fecha: date
    cliente: str
    pais: str
    producto: str
    importe: Decimal
    estado: str


@dataclass
class CleaningResult:
    rows_read: int = 0
    orders: list[Order] = field(default_factory=list)
    rejected: list[dict[str, str]] = field(default_factory=list)  # original row + "motivo"
    duplicates: int = 0
    conflicting_duplicates: int = 0  # same pedido_id with different data: a data quality alert
    fixes: Counter[str] = field(default_factory=Counter)  # fields fixed in loaded rows

    def rejection_reasons(self) -> Counter[str]:
        return Counter(reason for row in self.rejected for reason in row["motivo"].split(";"))


def clean_row(row: dict[str, str]) -> tuple[Order | None, list[str], list[str]]:
    """Cleans one row. Returns (order or None, rejection reasons, fixed fields)."""
    raw = {column: row.get(column) or "" for column in CSV_COLUMNS}
    reasons = []

    pedido_id = normalize_text(raw["pedido_id"])
    if not pedido_id:
        reasons.append("pedido_id_vacio")
    fecha = parse_date(raw["fecha"])
    if fecha is None:
        reasons.append("fecha_invalida")
    importe = parse_amount(raw["importe"])
    if importe is None:
        reasons.append("importe_vacio" if not raw["importe"].strip() else "importe_invalido")
    cliente = normalize_text(raw["cliente"])
    if not cliente:
        reasons.append("cliente_vacio")
    pais = normalize_country(raw["pais"])
    if pais is None:
        reasons.append("pais_desconocido")
    producto = normalize_text(raw["producto"])
    if not producto:
        reasons.append("producto_vacio")
    estado = normalize_status(raw["estado"])
    if estado is None:
        reasons.append("estado_desconocido")

    if fecha is None or importe is None or pais is None or estado is None or reasons:
        return None, reasons, []

    order = Order(pedido_id, fecha, cliente, pais, producto, importe, estado)
    clean_values = {
        "fecha": fecha.isoformat(),
        "importe": str(importe),
        "cliente": cliente,
        "pais": pais,
        "producto": producto,
        "estado": estado,
    }
    fixes = [column for column, value in clean_values.items() if value != raw[column]]
    return order, [], fixes


def clean_orders(rows: Iterable[dict[str, str]]) -> CleaningResult:
    """Cleans every row. For each pedido_id, the first valid row is kept.

    Deduplication uses pedido_id after normalizing, so duplicates with different formatting are
    caught too. It does not use a business key: a customer can buy the same product twice on the
    same day.
    """
    result = CleaningResult()
    kept: dict[str, Order] = {}
    for row in rows:
        result.rows_read += 1
        order, reasons, fixes = clean_row(row)
        if order is None:
            result.rejected.append({**row, "motivo": ";".join(reasons)})
        elif order.pedido_id in kept:
            result.duplicates += 1
            if kept[order.pedido_id] != order:
                result.conflicting_duplicates += 1
        else:
            kept[order.pedido_id] = order
            result.orders.append(order)
            result.fixes.update(fixes)
    return result


def format_report(result: CleaningResult) -> str:
    conflicts = result.conflicting_duplicates
    lines = [
        f"Rows read:               {result.rows_read:>6}",
        f"Orders loaded:           {len(result.orders):>6}",
        f"Duplicates removed:      {result.duplicates:>6}"
        + (f"  ({conflicts} with different data)" if conflicts else ""),
        f"Rows rejected:           {len(result.rejected):>6}",
    ]
    lines += [f"  {reason:<23}{count:>6}" for reason, count in sorted(result.rejection_reasons().items())]
    lines.append("Fields fixed in loaded rows:")
    lines += [f"  {column:<23}{count:>6}" for column, count in sorted(result.fixes.items())]
    return "\n".join(lines)
