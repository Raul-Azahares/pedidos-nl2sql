"""Canonical domain values, shared by the generator, the cleaning step and the LLM prompt."""

# Columns of the orders CSV (the contract between the generator and the cleaning step)
CSV_COLUMNS = ("pedido_id", "fecha", "cliente", "pais", "producto", "importe", "estado")

COUNTRIES = ("España", "México", "Francia", "Alemania", "Italia", "Portugal")
STATUSES = ("completado", "cancelado", "pendiente", "devuelto")

# Business decision: only a completed order counts as a sale.
SALE_STATUS = "completado"
