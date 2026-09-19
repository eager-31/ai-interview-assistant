from contextlib import asynccontextmanager
from uuid import UUID, uuid4

import httpx
import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from sqlalchemy import delete, select

from app.core.db import create_engine_and_sessionmaker
from app.core.redis_client import create_redis
from app.main import app
from app.models import InterviewSession, User
from app.schemas.interview import FeedbackResponse
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
    def __init__(self):
        self.calls = 0

    def with_structured_output(self, schema):
        model = self

        class Evaluator:
            async def ainvoke(self, messages):
                model.calls += 1
                transcript = " | ".join(str(m.content) for m in messages)
                return FeedbackResponse(score=3, feedback=transcript, areas_of_improvement="n/a")

        return Evaluator()


@asynccontextmanager
async def running_app():
    """Starts the app (real Redis and Postgres) with only the LLM replaced by stubs."""
    async with app.router.lifespan_context(app):
        app.state.agent = build_agent(EchoModel(), app.state.agent.checkpointer)
        app.state.model = StubFeedbackModel()
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
