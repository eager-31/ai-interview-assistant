from contextlib import asynccontextmanager

from fastapi import FastAPI
from langchain.chat_models import init_chat_model
from langgraph.checkpoint.redis.aio import AsyncRedisSaver

from app.api import auth, interview
from app.core.config import settings
from app.core.db import create_engine_and_sessionmaker
from app.core.errors import register_error_handlers
from app.core.limiter import limiter
from app.core.logging import setup_logging
from app.core.redis_client import create_redis
from app.services.agent import build_agent
from app.services.session import SESSION_TTL_SECONDS

LLM_TIMEOUT_SECONDS = 60

setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    redis = create_redis()
    engine, db_sessionmaker = create_engine_and_sessionmaker()
    # max_retries counts attempts, so 1 means no retries. An agent turn must not be
    # retried: it could add the same messages to the conversation twice.
    model = init_chat_model(
        f"google_genai:{settings.gemini_model}",
        api_key=settings.google_api_key,
        timeout=LLM_TIMEOUT_SECONDS,
        max_retries=1,
    )
    ttl = {"default_ttl": SESSION_TTL_SECONDS // 60}
    async with AsyncRedisSaver.from_conn_string(settings.redis_url, ttl=ttl) as checkpointer:
        await checkpointer.asetup()
        app.state.redis = redis
        app.state.db_sessionmaker = db_sessionmaker
        app.state.model = model
        app.state.agent = build_agent(model, checkpointer)
        yield
    await redis.aclose()
    await engine.dispose()


app = FastAPI(title="AI Interview Assistant", lifespan=lifespan)
app.state.limiter = limiter
register_error_handlers(app)
app.include_router(auth.router)
app.include_router(interview.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
