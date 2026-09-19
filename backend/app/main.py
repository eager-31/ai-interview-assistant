from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langchain.chat_models import init_chat_model
from langgraph.checkpoint.redis.aio import AsyncRedisSaver

from app.api import auth, interview
from app.core.config import settings
from app.core.db import create_engine_and_sessionmaker
from app.core.errors import register_error_handlers
from app.core.limiter import limiter
from app.core.logging import setup_logging
from app.core.redis_client import CONNECT_TIMEOUT_SECONDS, create_redis
from app.services.agent import build_agent
from app.services.session import SESSION_TTL_SECONDS

LLM_TIMEOUT_SECONDS = 60

setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    redis = create_redis()
    http = httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0))
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
    connection_args = {"socket_connect_timeout": CONNECT_TIMEOUT_SECONDS}
    async with AsyncRedisSaver.from_conn_string(settings.redis_url, ttl=ttl, connection_args=connection_args) as checkpointer:
        await checkpointer.asetup()
        app.state.redis = redis
        app.state.http = http
        app.state.db_sessionmaker = db_sessionmaker
        app.state.model = model
        app.state.agent = build_agent(model, checkpointer)
        yield
    await app.state.http.aclose()
    await redis.aclose()
    await engine.dispose()


app = FastAPI(title="AI Interview Assistant", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
    # Without this the browser hides these headers from the frontend's JavaScript.
    expose_headers=["X-Question-Number", "X-Interview-Complete"],
)
app.state.limiter = limiter
register_error_handlers(app)
app.include_router(auth.router)
app.include_router(interview.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
