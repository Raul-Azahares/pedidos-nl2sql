.PHONY: install data test lint format

install: ## Install dependencies (including dev ones) from uv.lock
	uv sync

data: ## Generate the dirty orders CSV (deterministic: fixed seed)
	uv run python -m pedidos.generate

test: ## Run the tests (no API key or network needed)
	uv run pytest

lint: ## Check style and formatting
	uv run ruff check .
	uv run ruff format --check .

format: ## Apply formatting and automatic fixes
	uv run ruff format .
	uv run ruff check --fix .
