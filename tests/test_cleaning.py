import random
from collections import Counter
from datetime import date
from decimal import Decimal

import pytest

from pedidos import generate
from pedidos.cleaning import (
    clean_orders,
    normalize_country,
    normalize_status,
    normalize_text,
    parse_amount,
    parse_date,
)
from pedidos.domain import COUNTRIES, STATUSES


def row(**overrides: str) -> dict[str, str]:
    """A valid CSV row; each test only changes what it cares about."""
    base = {
        "pedido_id": "P00001",
        "fecha": "2025-03-15",
        "cliente": "Ana Ruiz",
        "pais": "España",
        "producto": "Tablet",
        "importe": "329.00",
        "estado": "completado",
    }
    return base | overrides


# --- Field rules ---


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2025-03-15", date(2025, 3, 15)),
        ("15/03/2025", date(2025, 3, 15)),
        ("2025/03/15", date(2025, 3, 15)),
        ("15-03-2025", date(2025, 3, 15)),
        (" 2025-03-15 ", date(2025, 3, 15)),
        ("03/04/2025", date(2025, 4, 3)),  # ambiguous: read as day/month
    ],
)
def test_parse_date_accepts_known_formats(raw, expected):
    assert parse_date(raw) == expected


@pytest.mark.parametrize("raw", ["", "N/A", "ayer", "2025-02-30", "31/04/2025", "2024-13-05"])
def test_parse_date_rejects_invalid_dates(raw):
    assert parse_date(raw) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("329.00", Decimal("329.00")),
        ("339,15", Decimal("339.15")),  # decimal comma
        (" 12 ", Decimal("12.00")),
        ("10.005", Decimal("10.01")),  # rounded to cents, half up
    ],
)
def test_parse_amount_normalizes_valid_amounts(raw, expected):
    assert parse_amount(raw) == expected


@pytest.mark.parametrize("raw", ["", "  ", "abc", "0", "-5.00", "NaN", "1.234,56"])
def test_parse_amount_rejects_empty_garbage_and_non_positive(raw):
    assert parse_amount(raw) is None


@pytest.mark.parametrize(
    ("canonical", "variant"),
    [(country, v) for country, variants in generate.COUNTRY_VARIANTS.items() for v in variants],
)
def test_every_country_variant_from_the_generator_is_recognized(canonical, variant):
    assert normalize_country(variant) == canonical


def test_unknown_country_is_not_guessed():
    assert normalize_country("Atlántida") is None


@pytest.mark.parametrize("raw", ["completado", " Completado ", "COMPLETADO"])
def test_status_is_normalized(raw):
    assert normalize_status(raw) == "completado"


def test_unknown_status_is_rejected():
    assert normalize_status("enviado") is None


def test_normalize_text_collapses_whitespace():
    assert normalize_text("  Ana   Ruiz ") == "Ana Ruiz"


# --- Whole-row cleaning ---


def test_reformatted_duplicate_is_removed_keeping_the_first_row():
    rows = [row(), row(cliente=" Ana  Ruiz ", pais="ESPAÑA"), row(pedido_id="P00002")]
    result = clean_orders(rows)
    assert [o.pedido_id for o in result.orders] == ["P00001", "P00002"]
    assert result.duplicates == 1
    assert result.conflicting_duplicates == 0


def test_duplicate_with_different_data_is_flagged():
    result = clean_orders([row(), row(importe="999.00")])
    assert result.duplicates == 1
    assert result.conflicting_duplicates == 1
    assert result.orders[0].importe == Decimal("329.00")


def test_invalid_row_is_rejected_with_every_reason():
    result = clean_orders([row(fecha="31/04/2025", importe="")])
    assert result.orders == []
    assert result.rejected[0]["motivo"] == "fecha_invalida;importe_vacio"


def test_rejected_copy_does_not_hide_a_later_valid_copy():
    result = clean_orders([row(importe=""), row()])
    assert len(result.orders) == 1
    assert len(result.rejected) == 1
    assert result.duplicates == 0


def test_fixed_fields_are_counted():
    result = clean_orders([row(fecha="15/03/2025", importe="329,00", pais="ES", estado=" Completado ")])
    assert result.fixes == Counter({"fecha": 1, "importe": 1, "pais": 1, "estado": 1})


# --- Contract with the generator ---


def test_generator_catalog_matches_the_domain():
    assert set(generate.COUNTRY_WEIGHTS) == set(COUNTRIES)
    assert set(generate.STATUS_WEIGHTS) == set(STATUSES)


def test_generated_dataset_cleans_into_a_consistent_result():
    rng = random.Random(42)
    rows, _ = generate.inject_errors(generate.generate_orders(1200, rng), rng)

    result = clean_orders(rows)

    assert result.rows_read == len(rows) >= 1000
    assert len(result.orders) + len(result.rejected) + result.duplicates == result.rows_read
    ids = [o.pedido_id for o in result.orders]
    assert len(ids) == len(set(ids))
    assert {o.pais for o in result.orders} <= set(COUNTRIES)
    assert {o.estado for o in result.orders} <= set(STATUSES)
    # Only orders with unrecoverable errors are lost; no valid order is left out.
    assert set(result.rejection_reasons()) <= {"fecha_invalida", "importe_vacio"}
    lost_ids = {r["pedido_id"] for r in result.rejected}
    assert len(result.orders) == 1200 - len(lost_ids)
    assert result.conflicting_duplicates == 0
