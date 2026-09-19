import io
import json
import logging
from unittest.mock import AsyncMock

import httpx
import pytest
import redis.exceptions
from langchain_google_genai.chat_models import (
    ChatGoogleGenerativeAIError,
    GoogleAPIError,
    GoogleAuthenticationError,
    GoogleModelNotFoundError,
    GoogleRateLimitError,
)
from sqlalchemy.exc import OperationalError

from app.core.config import settings
from app.core.logging import JsonFormatter, session_id_var
from app.main import LLM_TIMEOUT_SECONDS, app
from app.services import records
from tests.test_sessions import run_interview


class FailingAgent:
    def __init__(self, error: Exception):
        self.error = error
        self.calls = 0

    async def ainvoke(self, *args, **kwargs):
        self.calls += 1
        raise self.error


class FailingFeedbackModel:
    def __init__(self, error: Exception):
        self.error = error
        self.calls = 0

    def with_structured_output(self, schema):
        model = self

        class Evaluator:
            async def ainvoke(self, messages):
                model.calls += 1
                raise model.error

        return Evaluator()


LLM_FAILURES = [
    (GoogleRateLimitError("quota exceeded"), 429, "llm_rate_limited"),
    (httpx.ConnectTimeout("timed out"), 504, "llm_timeout"),
    (TimeoutError(), 504, "llm_timeout"),
    (GoogleAuthenticationError("bad key"), 502, "llm_auth_failed"),
    (GoogleModelNotFoundError("no such model"), 502, "llm_auth_failed"),
    (GoogleAPIError(503, {"error": {"message": "high demand", "status": "UNAVAILABLE"}}), 503, "llm_unavailable"),
    (GoogleAPIError(500, {"error": {"message": "internal", "status": "INTERNAL"}}), 502, "llm_error"),
    (ChatGoogleGenerativeAIError("boom"), 502, "llm_error"),
    (httpx.ConnectError("unreachable"), 502, "llm_error"),
]


@pytest.mark.parametrize("error,status,code", LLM_FAILURES, ids=lambda v: type(v).__name__ if isinstance(v, Exception) else str(v))
async def test_llm_failures_map_to_distinct_responses_and_are_not_retried(client, error, status, code):
    app.state.agent = FailingAgent(error)

    response = await client.post("/api/interview/start", data={"subject": "Python"})

    assert response.status_code == status
    assert response.json()["detail"]["error"] == code
    assert response.json()["detail"]["message"]
    assert app.state.agent.calls == 1


async def test_failed_start_leaves_no_interview_behind(client):
    app.state.agent = FailingAgent(GoogleRateLimitError("quota"))
    await client.post("/api/interview/start", data={"subject": "Python"})

    assert (await client.get("/api/interview/history")).json() == []


async def test_failed_answer_does_not_advance_the_interview(client, created_sessions):
    session_id, _ = await run_interview(client, created_sessions, "Python", ["first-answer"])
    working_agent = app.state.agent

    app.state.agent = FailingAgent(GoogleRateLimitError("quota"))
    failed = await client.post("/api/interview/submit-answer", json={"session_id": session_id, "answer": "lost-answer"})
    assert failed.status_code == 429

    app.state.agent = working_agent
    retried = await client.post("/api/interview/submit-answer", json={"session_id": session_id, "answer": "second-answer"})
    assert retried.json()["question_number"] == 3

    detail = (await client.get(f"/api/interview/{session_id}")).json()
    assert [t["answer_text"] for t in detail["turns"]] == ["first-answer", "second-answer", None]


async def test_failed_feedback_saves_nothing_and_can_be_retried(client, created_sessions):
    session_id, _ = await run_interview(client, created_sessions, "Python", [f"ans-{i}" for i in range(5)])
    working_model = app.state.model

    app.state.model = FailingFeedbackModel(GoogleRateLimitError("quota"))
    failed = await client.post("/api/interview/get-feedback", json={"session_id": session_id})
    assert failed.status_code == 429
    assert app.state.model.calls == 1
    assert (await client.get(f"/api/interview/{session_id}")).json()["feedback"] is None

    app.state.model = working_model
    assert (await client.post("/api/interview/get-feedback", json={"session_id": session_id})).status_code == 200


async def test_redis_outage_returns_503(client, created_sessions, monkeypatch):
    session_id, _ = await run_interview(client, created_sessions, "Python", ["one"])
    monkeypatch.setattr(app.state.redis, "hgetall", AsyncMock(side_effect=redis.exceptions.ConnectionError("down")))

    response = await client.post("/api/interview/submit-answer", json={"session_id": session_id, "answer": "two"})

    assert response.status_code == 503
    assert response.json()["detail"]["error"] == "session_store_unavailable"


async def test_database_outage_returns_503(client, monkeypatch):
    error = OperationalError("SELECT 1", {}, Exception("connection refused"))
    monkeypatch.setattr(records, "list_interviews", AsyncMock(side_effect=error))

    response = await client.get("/api/interview/history")

    assert response.status_code == 503
    assert response.json()["detail"]["error"] == "database_unavailable"


async def test_unexpected_error_is_json_not_a_bare_500(client, monkeypatch):
    monkeypatch.setattr(records, "list_interviews", AsyncMock(side_effect=RuntimeError("a bug")))
    quiet = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
        headers=client.headers,
    )

    async with quiet:
        response = await quiet.get("/api/interview/history")

    assert response.status_code == 500
    assert response.json()["detail"]["error"] == "internal_error"
    assert "a bug" not in response.text


async def test_submit_answer_is_rate_limited_per_user(client, other_client, created_sessions, monkeypatch):
    session_id, _ = await run_interview(client, created_sessions, "Python", [])
    other_session, _ = await run_interview(other_client, created_sessions, "Go", [])
    monkeypatch.setattr(settings, "submit_answer_rate_limit", "2/minute")

    def submit(c, sid):
        return c.post("/api/interview/submit-answer", json={"session_id": sid, "answer": "x"})

    assert (await submit(client, session_id)).status_code == 200
    assert (await submit(client, session_id)).status_code == 200
    limited = await submit(client, session_id)
    assert limited.status_code == 429
    assert limited.json()["detail"]["error"] == "rate_limited"

    assert (await submit(other_client, other_session)).status_code == 200


def test_json_formatter_emits_one_json_object_with_session_id():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("json-format-test")
    logger.propagate = False
    logger.addHandler(handler)

    token = session_id_var.set("abc-123")
    try:
        logger.info("hello", extra={"question_number": 2})
    finally:
        session_id_var.reset(token)

    line = json.loads(stream.getvalue())
    assert line["message"] == "hello"
    assert line["level"] == "INFO"
    assert line["session_id"] == "abc-123"
    assert line["question_number"] == 2


async def test_route_logs_carry_the_session_id_and_never_the_answer(client, created_sessions, caplog):
    caplog.set_level(logging.INFO)
    session_id, _ = await run_interview(client, created_sessions, "Python", ["my-private-answer-text"])

    app_records = [r for r in caplog.records if r.name.startswith("app.")]
    assert {"interview started", "answer recorded"} <= {r.getMessage() for r in app_records}
    assert all(r.session_id == session_id for r in app_records)

    rendered = " ".join(JsonFormatter().format(r) for r in caplog.records)
    assert "my-private-answer-text" not in rendered


async def test_llm_failure_is_logged_with_the_session_id(client, caplog):
    caplog.set_level(logging.WARNING)
    app.state.agent = FailingAgent(GoogleRateLimitError("quota"))

    await client.post("/api/interview/start", data={"subject": "Python"})

    failure = next(r for r in caplog.records if r.getMessage() == "llm call failed")
    assert failure.session_id is not None
    assert failure.error == "llm_rate_limited"


async def test_real_gemini_client_has_a_timeout_and_no_hidden_retries():
    async with app.router.lifespan_context(app):
        model = app.state.model
        assert model.max_retries == 1  # attempts, not retries: 1 means a single try
        assert model.timeout == LLM_TIMEOUT_SECONDS
