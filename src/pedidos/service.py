"""Answers a question: LLM -> SQL validation -> read-only execution.

Kept apart from the HTTP layer so it can be reused (a CLI, an evaluation script) and tested alone.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pedidos.db import run_query
from pedidos.errors import AppError, QuestionNotAnswerableError
from pedidos.llm import SQLGenerator
from pedidos.sql_guard import validate_sql

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Answer:
    question: str
    sql: str
    explanation: str
    columns: list[str]
    rows: list[list[Any]]
    truncated: bool


def answer_question(
    question: str,
    generator: SQLGenerator,
    db_path: Path,
    *,
    max_rows: int = 500,
    timeout_s: float = 5.0,
) -> Answer:
    generation = generator.generate(question)
    if generation.sql is None:
        raise QuestionNotAnswerableError(
            generation.explanation or "La pregunta no se puede responder con los datos disponibles."
        )
    try:
        validate_sql(generation.sql)
        result = run_query(db_path, generation.sql, max_rows=max_rows, timeout_s=timeout_s)
    except AppError as error:
        error.sql = generation.sql  # the client sees which SQL was rejected or failed
        logger.warning("Rejected SQL (%s): %s", error.code, generation.sql)
        raise
    logger.info("Answered with %d rows: %s", len(result.rows), generation.sql)
    rows = [[value.hex() if isinstance(value, bytes) else value for value in row] for row in result.rows]
    return Answer(question, generation.sql, generation.explanation, result.columns, rows, result.truncated)
