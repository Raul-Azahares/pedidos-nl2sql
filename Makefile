.PHONY: install test lint format

install: ## Instala dependencias (incluidas las de desarrollo) desde uv.lock
	uv sync

test: ## Ejecuta los tests (no necesitan API key ni red)
	uv run pytest

lint: ## Comprueba estilo y formato
	uv run ruff check .
	uv run ruff format --check .

format: ## Aplica formato y arreglos automáticos
	uv run ruff format .
	uv run ruff check --fix .
