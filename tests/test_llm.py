"""Gemini client tests. httpx.MockTransport replaces the network, so no key or connection is needed."""

import json

import httpx
import pytest

from pedidos.errors import LLMInvalidOutputError, LLMTimeoutError, LLMUnavailableError
from pedidos.llm import GeminiSQLGenerator, SQLGeneration


def gemini_reply(text: str, finish_reason: str = "STOP") -> dict:
    """A response shaped like Gemini's generateContent."""
    return {
        "candidates": [
            {"content": {"role": "model", "parts": [{"text": text}]}, "finishReason": finish_reason}
        ],
        "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5},
    }


def make_generator(handler, api_key: str = "test-key") -> GeminiSQLGenerator:
    return GeminiSQLGenerator(
        api_key=api_key,
        model="gemini-test",
        system_prompt="PROMPT",
        transport=httpx.MockTransport(handler),
    )


def test_returns_the_sql_and_the_explanation():
    reply = json.dumps({"sql": "SELECT 1", "explanation": "Una prueba."})
    generator = make_generator(lambda request: httpx.Response(200, json=gemini_reply(reply)))
    assert generator.generate("¿Algo?") == SQLGeneration(sql="SELECT 1", explanation="Una prueba.")


def test_request_carries_the_prompt_the_question_the_schema_and_the_key():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["request"] = request
        return httpx.Response(200, json=gemini_reply('{"sql": null, "explanation": "x"}'))

    make_generator(handler).generate("¿Cuánto vendimos?")

    request = seen["request"]
    body = json.loads(request.content)
    assert request.url.path.endswith("/models/gemini-test:generateContent")
    assert request.headers["x-goog-api-key"] == "test-key"
    assert "test-key" not in str(request.url)  # never in the URL, where it could end up in logs
    assert body["systemInstruction"]["parts"][0]["text"] == "PROMPT"
    assert body["contents"][0]["parts"][0]["text"] == "¿Cuánto vendimos?"
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    assert body["generationConfig"]["responseJsonSchema"]["required"] == ["sql", "explanation"]


@pytest.mark.parametrize("sql", [None, "", "   "])
def test_null_or_blank_sql_means_the_question_cannot_be_answered(sql):
    reply = json.dumps({"sql": sql, "explanation": "No hay datos de stock."})
    generator = make_generator(lambda request: httpx.Response(200, json=gemini_reply(reply)))
    assert generator.generate("¿Cuánto stock queda?").sql is None


def test_reasoning_parts_from_thinking_models_are_ignored():
    payload = gemini_reply('{"sql": "SELECT 1", "explanation": "x"}')
    payload["candidates"][0]["content"]["parts"].insert(0, {"text": "Pensando...", "thought": True})
    generator = make_generator(lambda request: httpx.Response(200, json=payload))
    assert generator.generate("¿Algo?").sql == "SELECT 1"


@pytest.mark.parametrize(
    ("response", "error", "message"),
    [
        (httpx.Response(429, json={"error": {"status": "RESOURCE_EXHAUSTED"}}), LLMUnavailableError, "cuota"),
        (
            httpx.Response(400, json={"error": {"details": [{"reason": "API_KEY_INVALID"}]}}),
            LLMUnavailableError,
            "API key",
        ),
        (
            httpx.Response(403, json={"error": {"status": "PERMISSION_DENIED"}}),
            LLMUnavailableError,
            "API key",
        ),
        (httpx.Response(404, json={"error": {"status": "NOT_FOUND"}}), LLMUnavailableError, "LLM_MODEL"),
        (httpx.Response(503, json={"error": {"status": "UNAVAILABLE"}}), LLMUnavailableError, "HTTP 503"),
        (httpx.Response(200, text="<html>no es JSON</html>"), LLMInvalidOutputError, "formato"),
        (httpx.Response(200, json=gemini_reply("esto no es JSON")), LLMInvalidOutputError, "formato"),
        (httpx.Response(200, json=gemini_reply('{"query": "SELECT 1"}')), LLMInvalidOutputError, "formato"),
        (
            httpx.Response(200, json=gemini_reply('{"sql": "SELE', "MAX_TOKENS")),
            LLMInvalidOutputError,
            "MAX_TOKENS",
        ),
        (
            httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}}),
            LLMInvalidOutputError,
            "SAFETY",
        ),
    ],
    ids=[
        "quota",
        "invalid_key",
        "forbidden",
        "unknown_model",
        "provider_down",
        "body_not_json",
        "answer_not_json",
        "answer_wrong_shape",
        "answer_cut_off",
        "question_blocked",
    ],
)
def test_provider_failures_become_clear_errors(response, error, message):
    generator = make_generator(lambda request: response)
    with pytest.raises(error, match=message):
        generator.generate("¿Cuánto vendimos?")


def test_timeout_becomes_an_llm_timeout():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    with pytest.raises(LLMTimeoutError):
        make_generator(handler).generate("¿Cuánto vendimos?")


def test_network_error_becomes_llm_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host", request=request)

    with pytest.raises(LLMUnavailableError, match="conectar"):
        make_generator(handler).generate("¿Cuánto vendimos?")


def test_missing_key_fails_without_calling_the_provider():
    def handler(request: httpx.Request) -> httpx.Response:
        pytest.fail("no request should be sent without an API key")

    with pytest.raises(LLMUnavailableError, match="GEMINI_API_KEY"):
        make_generator(handler, api_key="").generate("¿Cuánto vendimos?")
