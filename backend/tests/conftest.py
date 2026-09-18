from contextlib import asynccontextmanager
from uuid import UUID

import httpx
import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from sqlalchemy import delete

from app.core.db import create_engine_and_sessionmaker
from app.core.redis_client import create_redis
from app.main import app
from app.models import InterviewSession
from app.schemas.interview import FeedbackResponse
from app.services.agent import build_agent


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


@pytest.fixture
async def client():
    async with running_app() as c:
        yield c


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
