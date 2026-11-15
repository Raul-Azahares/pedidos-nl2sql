"""HTTP API: POST /ask answers a natural-language question with data from the database.

Run it with `make api` and open http://127.0.0.1:8000/docs for the interactive documentation.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, StringConstraints

from pedidos.config import Settings
from pedidos.db import connect_read_only
from pedidos.errors import AppError
from pedidos.llm import GeminiSQLGenerator, SQLGenerator
from pedidos.prompt import build_system_prompt
from pedidos.service import answer_question

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# 4xx: this question cannot be answered safely, so retrying the same question won't help.
# 5xx: a dependency (the LLM or the database) failed, and retrying later may work.
STATUS_BY_CODE = {
    "INVALID_REQUEST": 422,
    "QUESTION_NOT_ANSWERABLE": 422,
    "QUERY_NOT_ALLOWED": 422,
    "QUERY_FAILED": 422,
    "LLM_INVALID_OUTPUT": 502,
    "LLM_UNAVAILABLE": 503,
    "DB_UNAVAILABLE": 503,
    "LLM_TIMEOUT": 504,
    "QUERY_TIMEOUT": 504,
}

app = FastAPI(
    title="pedidos-nl2sql",
    description="Preguntas en lenguaje natural sobre los pedidos, respondidas con SQL validada.",
    version="0.1.0",
)


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_generator() -> SQLGenerator:
    """The real LLM. Built on first use, so the API starts even without a key or a database."""
    settings = get_settings()
    return GeminiSQLGenerator(
        api_key=settings.gemini_api_key.get_secret_value(),
        model=settings.llm_model,
        system_prompt=build_system_prompt(settings.db_path),
        timeout_s=settings.llm_timeout_s,
    )


class AskRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"question": "¿Cuánto vendimos en España en marzo?"}]}
    )

    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]


class AskResponse(BaseModel):
    question: str
    sql: str
    explanation: str
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    truncated: bool


class ErrorDetail(BaseModel):
    code: str
    message: str
    sql: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status: {"model": ErrorResponse} for status in sorted(set(STATUS_BY_CODE.values()))
}


@app.post("/ask", response_model=AskResponse, responses=ERROR_RESPONSES)
def ask(
    request: AskRequest,
    generator: Annotated[SQLGenerator, Depends(get_generator)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AskResponse:
    answer = answer_question(
        request.question,
        generator,
        settings.db_path,
        max_rows=settings.max_rows,
        timeout_s=settings.query_timeout_s,
    )
    return AskResponse(
        question=answer.question,
        sql=answer.sql,
        explanation=answer.explanation,
        columns=answer.columns,
        rows=answer.rows,
        row_count=len(answer.rows),
        truncated=answer.truncated,
    )


@app.get("/health", responses={503: {"model": ErrorResponse}})
def health(settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, str]:
    connect_read_only(settings.db_path).close()  # DB_UNAVAILABLE (503) if the ETL has not run
    return {"status": "ok"}


def _error(status: int, code: str, message: str, **extra: Any) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message, **extra}})


@app.exception_handler(AppError)
def handle_app_error(request: Request, error: AppError) -> JSONResponse:
    status = STATUS_BY_CODE.get(error.code, 500)
    logger.warning("%s %s -> %s %s: %s", request.method, request.url.path, status, error.code, error.message)
    extra = {"sql": error.sql} if error.sql else {}
    return _error(status, error.code, error.message, **extra)


@app.exception_handler(RequestValidationError)
def handle_invalid_request(request: Request, error: RequestValidationError) -> JSONResponse:
    return _error(
        422,
        "INVALID_REQUEST",
        "La petición no es válida: envía un JSON con 'question' (entre 3 y 500 caracteres).",
        details=jsonable_encoder(error.errors()),
    )


@app.exception_handler(Exception)
def handle_unexpected_error(request: Request, error: Exception) -> JSONResponse:
    logger.exception("Unexpected error on %s %s", request.method, request.url.path)
    return _error(500, "INTERNAL_ERROR", "Error interno inesperado.")
