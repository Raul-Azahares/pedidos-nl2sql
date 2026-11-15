"""Turns a natural-language question into SQL with Gemini.

The API depends on the SQLGenerator interface, not on Gemini: the tests use a fake generator, and
switching to another provider means writing another class. Gemini is called through its REST API
with httpx (the README explains why not the SDK). The answer is constrained to a JSON schema, so
there is no free text to parse.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, ValidationError, field_validator

from pedidos.errors import LLMInvalidOutputError, LLMTimeoutError, LLMUnavailableError

logger = logging.getLogger(__name__)

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

# JSON schema the model has to follow (Gemini's responseJsonSchema)
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "sql": {
            "type": ["string", "null"],
            "description": "A single read-only SQLite SELECT query, or null if the question "
            "cannot be answered with these tables.",
        },
        "explanation": {
            "type": "string",
            "description": "One sentence in Spanish on how the question was interpreted, "
            "including any assumption.",
        },
    },
    "required": ["sql", "explanation"],
}


class SQLGeneration(BaseModel):
    sql: str | None
    explanation: str

    @field_validator("sql")
    @classmethod
    def blank_sql_means_no_sql(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class SQLGenerator(Protocol):
    def generate(self, question: str) -> SQLGeneration: ...


class GeminiSQLGenerator:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        system_prompt: str,
        timeout_s: float = 20.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._system_prompt = system_prompt
        self._client = httpx.Client(base_url=GEMINI_BASE_URL, timeout=timeout_s, transport=transport)

    def generate(self, question: str) -> SQLGeneration:
        if not self._api_key:
            raise LLMUnavailableError("Falta la API key del LLM: define GEMINI_API_KEY en el fichero .env.")
        body = {
            "systemInstruction": {"parts": [{"text": self._system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": question}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseJsonSchema": RESPONSE_SCHEMA,
            },
        }
        started = time.monotonic()
        try:
            # The key travels in a header, never in the URL, where it could end up in logs.
            response = self._client.post(
                f"/models/{self._model}:generateContent",
                json=body,
                headers={"x-goog-api-key": self._api_key},
            )
        except httpx.TimeoutException as error:
            raise LLMTimeoutError("El LLM no ha respondido a tiempo.") from error
        except httpx.HTTPError as error:
            raise LLMUnavailableError("No se ha podido conectar con el proveedor del LLM.") from error

        _raise_for_status(response, self._model)
        try:
            payload = response.json()
        except ValueError as error:
            raise LLMInvalidOutputError(
                "El LLM no ha devuelto una respuesta con el formato esperado."
            ) from error
        usage = payload.get("usageMetadata") or {}
        logger.info(
            "LLM %s answered in %.2fs (%s input tokens, %s output tokens)",
            self._model,
            time.monotonic() - started,
            usage.get("promptTokenCount"),
            usage.get("candidatesTokenCount"),
        )
        return _parse_generation(payload)


def _raise_for_status(response: httpx.Response, model: str) -> None:
    status = response.status_code
    if status < 400:
        return
    logger.warning("LLM provider returned HTTP %s: %s", status, response.text[:500])
    if status == 429:
        raise LLMUnavailableError("Se ha superado la cuota del LLM. Inténtalo de nuevo más tarde.")
    if status in (401, 403) or (status == 400 and "API_KEY_INVALID" in response.text):
        raise LLMUnavailableError("El proveedor del LLM ha rechazado la API key. Revisa GEMINI_API_KEY.")
    if status == 404:
        raise LLMUnavailableError(f"El modelo {model} no existe o no está disponible. Revisa LLM_MODEL.")
    raise LLMUnavailableError(f"El proveedor del LLM ha devuelto un error (HTTP {status}).")


def _parse_generation(payload: dict[str, Any]) -> SQLGeneration:
    candidates = payload.get("candidates") or []
    if not candidates:
        reason = (payload.get("promptFeedback") or {}).get("blockReason", "sin respuesta")
        raise LLMInvalidOutputError(f"El LLM no ha generado ninguna respuesta (motivo: {reason}).")
    candidate = candidates[0]
    finish_reason = candidate.get("finishReason", "STOP")
    if finish_reason != "STOP":
        raise LLMInvalidOutputError(
            f"La respuesta del LLM está incompleta o bloqueada (motivo: {finish_reason})."
        )
    parts = (candidate.get("content") or {}).get("parts") or []
    # Thinking models may add reasoning parts; only the answer text matters.
    text = "".join(part.get("text", "") for part in parts if not part.get("thought"))
    try:
        return SQLGeneration.model_validate_json(text)
    except ValidationError as error:
        raise LLMInvalidOutputError("El LLM no ha devuelto una respuesta con el formato esperado.") from error
