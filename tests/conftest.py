from datetime import date
from decimal import Decimal

import pytest

from pedidos import etl
from pedidos.cleaning import CleaningResult, Order

# Small dataset with known results. For example, sales in Spain in March 2025:
# P1 + P2 = 300.00 (P3 is cancelled and P4 is from 2024, so they do not count).
SAMPLE_ORDERS = [
    Order("P1", date(2025, 3, 5), "Ana Ruiz", "España", "Tablet", Decimal("100.00"), "completado"),
    Order("P2", date(2025, 3, 20), "Luis Gil", "España", "Monitor", Decimal("200.00"), "completado"),
    Order("P3", date(2025, 3, 21), "Ana Ruiz", "España", "Ratón", Decimal("50.00"), "cancelado"),
    Order("P4", date(2024, 3, 10), "Ana Ruiz", "España", "Tablet", Decimal("70.00"), "completado"),
    Order("P5", date(2025, 3, 8), "Marie Dubois", "Francia", "Tablet", Decimal("300.00"), "completado"),
    Order("P6", date(2025, 4, 1), "Luis Gil", "España", "Teclado", Decimal("40.00"), "completado"),
]


@pytest.fixture
def sample_db(tmp_path):
    db_path = tmp_path / "pedidos.db"
    etl.load(CleaningResult(orders=SAMPLE_ORDERS), db_path)
    return db_path
