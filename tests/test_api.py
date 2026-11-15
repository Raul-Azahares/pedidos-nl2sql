"""Endpoint tests with a fake LLM and the sample database: no network and no API key."""

import pytest
from fastapi.testclient import TestClient

from pedidos.api import app, get_generator, get_settings
from pedidos.config import Settings
from pedidos.db import run_query
from pedidos.errors import LLMInvalidOutputError, LLMTimeoutError, LLMUnavailableError
from pedidos.llm import SQLGeneration

SPAIN_MARCH = (
    "SELECT ROUND(SUM(ventas), 2) AS ventas FROM ventas_mes_pais WHERE pais = 'España' AND mes = '2025-03'"
)


class FakeGenerator:
    """Stands in for Gemini: returns a fixed answer or raises a fixed error, and records questions."""

    def __init__(self, sql=None, explanation="Respuesta simulada.", error=None):
        self.sql = sql
        self.explanation = explanation
        self.error = error
        self.questions = []

    def generate(self, question):
        self.questions.append(question)
        if self.error is not None:
            raise self.error
        return SQLGeneration(sql=self.sql, explanation=self.explanation)


@pytest.fixture
def client(sample_db):
    """Returns a function that sets up the fake LLM and the settings, and gives back a TestClient."""

    def make(generator=None, **settings):
        settings.setdefault("db_path", sample_db)
        app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, **settings)
        app.dependency_overrides[get_generator] = lambda: generator or FakeGenerator()
        return TestClient(app)

    yield make
    app.dependency_overrides.clear()


def ask(test_client, question="¿Cuánto vendimos en España en marzo?"):
    return test_client.post("/ask", json={"question": question})


def test_answers_with_the_data_from_the_database(client):
    llm = FakeGenerator(sql=SPAIN_MARCH, explanation="Ventas de marzo de 2025.")
    response = ask(client(llm))

    assert response.status_code == 200
    assert response.json() == {
        "question": "¿Cuánto vendimos en España en marzo?",
        "sql": SPAIN_MARCH,
        "explanation": "Ventas de marzo de 2025.",
        "columns": ["ventas"],
        "rows": [[300.0]],  # P1 + P2 in the sample: the cancelled order and 2024 do not count
        "row_count": 1,
        "truncated": False,
    }
    assert llm.questions == ["¿Cuánto vendimos en España en marzo?"]


def test_a_write_from_the_llm_is_rejected_and_the_database_is_untouched(client, sample_db):
    response = ask(client(FakeGenerator(sql="DROP TABLE pedidos")), "Borra la tabla de pedidos")

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "QUERY_NOT_ALLOWED"
    assert error["sql"] == "DROP TABLE pedidos"
    assert run_query(sample_db, "SELECT COUNT(*) FROM pedidos").rows == [(6,)]


def test_a_table_outside_the_allowlist_is_rejected(client):
    response = ask(client(FakeGenerator(sql="SELECT * FROM sqlite_master")))

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "QUERY_NOT_ALLOWED"
    assert "sqlite_master" in response.json()["error"]["message"]


def test_a_question_the_llm_cannot_answer_returns_its_explanation(client):
    llm = FakeGenerator(sql=None, explanation="No hay datos de emails de clientes.")
    response = ask(client(llm), "¿Cuál es el email de Ana Ruiz?")

    assert response.status_code == 422
    assert response.json()["error"] == {
        "code": "QUESTION_NOT_ANSWERABLE",
        "message": "No hay datos de emails de clientes.",
    }


def test_valid_sql_that_fails_to_run_is_a_clear_error(client):
    response = ask(client(FakeGenerator(sql="SELECT email FROM pedidos")))

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "QUERY_FAILED"
    assert "email" in error["message"]


@pytest.mark.parametrize(
    ("llm_error", "status", "code"),
    [
        (LLMUnavailableError("Se ha superado la cuota del LLM."), 503, "LLM_UNAVAILABLE"),
        (LLMTimeoutError("El LLM no ha respondido a tiempo."), 504, "LLM_TIMEOUT"),
        (LLMInvalidOutputError("El LLM no ha devuelto JSON."), 502, "LLM_INVALID_OUTPUT"),
    ],
)
def test_llm_failures_become_clear_errors(client, llm_error, status, code):
    response = ask(client(FakeGenerator(error=llm_error)))

    assert response.status_code == status
    assert response.json()["error"] == {"code": code, "message": llm_error.message}


@pytest.mark.parametrize(
    "payload",
    [{"question": ""}, {"question": "   "}, {"question": "x" * 501}, {}, {"pregunta": "¿Cuánto?"}],
    ids=["empty", "blank", "too_long", "missing", "wrong_field"],
)
def test_invalid_requests_are_rejected_before_calling_the_llm(client, payload):
    llm = FakeGenerator(sql=SPAIN_MARCH)
    response = client(llm).post("/ask", json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_REQUEST"
    assert llm.questions == []


def test_large_results_are_capped_and_flagged(client):
    llm = FakeGenerator(sql="SELECT pedido_id FROM pedidos ORDER BY pedido_id")
    body = ask(client(llm, max_rows=2)).json()

    assert body["rows"] == [["P1"], ["P2"]]
    assert body["row_count"] == 2
    assert body["truncated"] is True


def test_missing_database_is_reported_on_ask_and_health(client, tmp_path):
    test_client = client(FakeGenerator(sql=SPAIN_MARCH), db_path=tmp_path / "no_existe.db")

    for response in (ask(test_client), test_client.get("/health")):
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "DB_UNAVAILABLE"
        assert "make etl" in response.json()["error"]["message"]


def test_health_is_ok_when_the_database_exists(client):
    response = client().get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
