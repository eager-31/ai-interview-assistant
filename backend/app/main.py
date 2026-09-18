from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from langchain.chat_models import init_chat_model
from langgraph.checkpoint.redis.aio import AsyncRedisSaver

from app.api import interview
from app.core.config import settings
from app.core.redis_client import create_redis
from app.services.agent import build_agent
from app.services.session import SESSION_TTL_SECONDS, SessionNotFound


@asynccontextmanager
async def lifespan(app: FastAPI):
    redis = create_redis()
    model = init_chat_model(f"google_genai:{settings.gemini_model}", api_key=settings.google_api_key)
    ttl = {"default_ttl": SESSION_TTL_SECONDS // 60}
    async with AsyncRedisSaver.from_conn_string(settings.redis_url, ttl=ttl) as checkpointer:
        await checkpointer.asetup()
        app.state.redis = redis
        app.state.model = model
        app.state.agent = build_agent(model, checkpointer)
        yield
    await redis.aclose()


app = FastAPI(title="AI Interview Assistant", lifespan=lifespan)
app.include_router(interview.router)


@app.exception_handler(SessionNotFound)
async def session_not_found_handler(request: Request, exc: SessionNotFound):
    return JSONResponse(
        status_code=404,
        content={"detail": {"error": "session_not_found", "message": "Session does not exist or has expired."}},
    )


@app.get("/health")
async def health():
    return {"status": "ok"}
