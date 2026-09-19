from contextlib import asynccontextmanager
from uuid import UUID, uuid4

import httpx
import pytest
from tenacity import wait_none
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from sqlalchemy import delete, select

from app.core import retry
from app.core.config import settings
from app.core.db import create_engine_and_sessionmaker
from app.core.limiter import limiter
from app.core.redis_client import create_redis
from app.main import app
from app.models import InterviewSession, User
from app.schemas.interview import AnswerScore, BackgroundSummary, FeedbackEvaluation
from app.services import stt
from app.services.agent import build_agent


PASSWORD = "correct-horse-battery"
TEST_EMAIL_PATTERN = "pytest-%@example.com"


async def sign_up(client) -> str:
    email = f"pytest-{uuid4().hex[:12]}@example.com"
    response = await client.post("/api/auth/register", json={"email": email, "password": PASSWORD})
    assert response.status_code == 201
    return email


async def log_in(client, email: str) -> dict[str, str]:
    response = await client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


class EchoModel(BaseChatModel):
    """Replies with the last message it was given, so tests can see what each session's history contained."""

    @property
    def _llm_type(self) -> str:
        return "echo"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        reply = AIMessage(content=f"echo: {messages[-1].content}")
        return ChatResult(generations=[ChatGeneration(message=reply)])


class StubFeedbackModel:
    """Stands in for the real model wherever the app asks for structured output.

    Answers containing "strong" are graded 5/5/5 and "weak" 1/2/1; anything else is 3/3/3.
    """

    def __init__(self):
        self.calls = 0
        self.summary_calls = 0
        self.score_calls = 0
        self.last_summary_input = None
        self.score_inputs: list[str] = []

    async def grade(self, prompt: str) -> AnswerScore:
        self.score_calls += 1
        self.score_inputs.append(prompt)
        answer = prompt.split("Answer:")[-1]
        if "strong" in answer:
            return AnswerScore(correctness=5, clarity=5, depth=5, comment="Strong answer.")
        if "weak" in answer:
            return AnswerScore(correctness=1, clarity=2, depth=1, comment="Weak answer.")
        return AnswerScore(correctness=3, clarity=3, depth=3, comment="Adequate answer.")

    def with_structured_output(self, schema):
        model = self

        class Evaluator:
            async def ainvoke(self, messages):
                if schema is AnswerScore:
                    return await model.grade(str(messages))
                if schema is BackgroundSummary:
                    model.summary_calls += 1
                    model.last_summary_input = messages
                    return BackgroundSummary(
                        target_role="Stub Role",
                        key_skills=[w for w in str(messages).replace("\n", " ").split() if w.startswith("skill-")],
                        experience_summary="Stub experience.",
                    )
                model.calls += 1
                transcript = " | ".join(str(m.content) for m in messages)
                return FeedbackEvaluation(overall_score=3, feedback=transcript, areas_of_improvement="n/a")

        return Evaluator()


class FakeSpeechServices:
    """Plays the part of AssemblyAI and Murf at the HTTP level, so the real service code runs against it."""

    AUDIO = b"ID3-fake-mp3-bytes"

    def __init__(self):
        self.transcript = "a strong spoken answer"
        self.transcript_error: str | None = None
        self.polls_before_done = 1
        self.murf_stream: httpx.AsyncByteStream | None = None
        self.requests: list[httpx.Request] = []
        self.failures: dict[str, list] = {}
        self._polls = 0

    def fail(self, step: str, *outcomes):
        """The next calls to `step` (upload, transcript, poll or murf) answer with these statuses or raise these errors."""
        self.failures.setdefault(step, []).extend(outcomes)

    def calls(self, step: str) -> list[httpx.Request]:
        return [r for r in self.requests if self._step(r) == step]

    @staticmethod
    def _step(request: httpx.Request) -> str:
        if request.url.host == "global.api.murf.ai":
            return "murf"
        return {"/v2/upload": "upload", "/v2/transcript": "transcript"}.get(request.url.path, "poll")

    def __call__(self, request: httpx.Request) -> httpx.Response:
        step = self._step(request)
        self.requests.append(request)
        if self.failures.get(step):
            outcome = self.failures[step].pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return httpx.Response(outcome, json={"error": "injected failure"})

        if step == "upload":
            return httpx.Response(200, json={"upload_url": "https://cdn.assemblyai.com/upload/fake"})
        if step == "transcript":
            return httpx.Response(200, json={"id": "tr-1", "status": "queued"})
        if step == "poll":
            self._polls += 1
            if self.transcript_error:
                return httpx.Response(200, json={"status": "error", "error": self.transcript_error})
            if self._polls <= self.polls_before_done:
                return httpx.Response(200, json={"status": "processing"})
            return httpx.Response(200, json={"status": "completed", "text": self.transcript})
        if self.murf_stream is not None:
            return httpx.Response(200, stream=self.murf_stream, headers={"content-type": "audio/mpeg"})
        return httpx.Response(200, content=self.AUDIO, headers={"content-type": "audio/mpeg"})


def mock_http(fake: FakeSpeechServices) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(fake))


@pytest.fixture(autouse=True)
def _speech_test_settings(monkeypatch):
    monkeypatch.setattr(settings, "assemblyai_api_key", "test-assemblyai-key")
    monkeypatch.setattr(settings, "murf_api_key", "test-murf-key")
    monkeypatch.setattr(retry, "RETRY_WAIT", wait_none())
    monkeypatch.setattr(stt, "POLL_INTERVAL_SECONDS", 0)


@asynccontextmanager
async def running_app():
    """Starts the app (real Redis and Postgres) with only the LLM replaced by stubs."""
    async with app.router.lifespan_context(app):
        app.state.agent = build_agent(EchoModel(), app.state.agent.checkpointer)
        app.state.model = StubFeedbackModel()
        app.state.speech = FakeSpeechServices()
        await app.state.http.aclose()
        app.state.http = mock_http(app.state.speech)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


def _new_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.fixture
async def client():
    """A client already logged in as a fresh user."""
    async with running_app() as c:
        c.headers.update(await log_in(c, await sign_up(c)))
        yield c


@pytest.fixture
async def other_client(client):
    """A second, separate user talking to the same running app."""
    async with _new_client() as c:
        c.headers.update(await log_in(c, await sign_up(c)))
        yield c


@pytest.fixture
async def anonymous_client(client):
    async with _new_client() as c:
        yield c


@pytest.fixture(autouse=True)
def _relaxed_rate_limit(monkeypatch):
    """Tests submit many answers quickly; the rate-limit test sets its own low limit."""
    monkeypatch.setattr(settings, "submit_answer_rate_limit", "1000/minute")
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture(autouse=True)
async def _delete_test_users():
    yield
    # Runs after every other fixture is torn down. Interviews go first: their user_id FK has no cascade.
    engine, sessionmaker = create_engine_and_sessionmaker()
    async with sessionmaker() as db:
        test_users = select(User.id).where(User.email.like(TEST_EMAIL_PATTERN))
        await db.execute(delete(InterviewSession).where(InterviewSession.user_id.in_(test_users)))
        await db.execute(delete(User).where(User.id.in_(test_users)))
        await db.commit()
    await engine.dispose()


@pytest.fixture
async def created_sessions():
    ids: list[str] = []
    yield ids
    # Own connections, so cleanup works even if the test restarted the app.
    redis = create_redis()
    engine, sessionmaker = create_engine_and_sessionmaker()
    for session_id in ids:
        async for key in redis.scan_iter(match=f"*{session_id}*"):
            await redis.delete(key)
    async with sessionmaker() as db:
        await db.execute(delete(InterviewSession).where(InterviewSession.id.in_([UUID(i) for i in ids])))
        await db.commit()
    await redis.aclose()
    await engine.dispose()
