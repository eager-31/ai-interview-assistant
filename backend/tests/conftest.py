import httpx
import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from app.main import app
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


class _StubEvaluator:
    async def ainvoke(self, messages):
        transcript = " | ".join(str(m.content) for m in messages)
        return FeedbackResponse(score=3, feedback=transcript, areas_of_improvement="n/a")


class StubFeedbackModel:
    def with_structured_output(self, schema):
        return _StubEvaluator()


@pytest.fixture
async def client():
    async with app.router.lifespan_context(app):
        # Keep the real Redis and checkpointer from the lifespan; only the LLM is replaced.
        app.state.agent = build_agent(EchoModel(), app.state.agent.checkpointer)
        app.state.model = StubFeedbackModel()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


@pytest.fixture
async def created_sessions(client):
    ids: list[str] = []
    yield ids
    redis = app.state.redis
    for session_id in ids:
        async for key in redis.scan_iter(match=f"*{session_id}*"):
            await redis.delete(key)
