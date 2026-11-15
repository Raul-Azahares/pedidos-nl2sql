.PHONY: install data etl api test lint format

install: ## Install dependencies (including dev ones) from uv.lock
	uv sync

data: ## Generate the dirty orders CSV (deterministic: fixed seed)
	uv run python -m pedidos.generate

etl: ## Clean the CSV and load it into SQLite (data/pedidos.db) along with the views
	uv run python -m pedidos.etl

api: ## Start the API on http://127.0.0.1:8000 (interactive docs at /docs)
	uv run uvicorn pedidos.api:app --reload

test: ## Run the tests (no API key or network needed)
	uv run pytest

lint: ## Check style and formatting
	uv run ruff check .
	uv run ruff format --check .

format: ## Apply formatting and automatic fixes
	uv run ruff format .
	uv run ruff check --fix .
