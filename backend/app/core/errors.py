import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from langchain_core.exceptions import (
    ModelAuthenticationError,
    ModelError,
    ModelNotFoundError,
    ModelPermissionDeniedError,
    ModelRateLimitError,
    ModelTimeoutError,
)
from langchain_google_genai.chat_models import ChatGoogleGenerativeAIError, GoogleAPIError
from redis.exceptions import RedisError
from slowapi.errors import RateLimitExceeded
from sqlalchemy.exc import InterfaceError, OperationalError

from app.services.session import SessionNotFound

logger = logging.getLogger(__name__)


class ApiError(Exception):
    def __init__(self, status_code: int, error: str, message: str):
        self.status_code = status_code
        self.error = error
        self.message = message


def _response(status_code: int, error: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": {"error": error, "message": message}})


@asynccontextmanager
async def llm_errors():
    """Turns Gemini failures into ApiErrors. Deliberately no retry here: re-running an
    agent turn can append the same messages to the conversation history twice."""
    try:
        yield
    except ModelRateLimitError as exc:
        raise _llm_failure(exc, 429, "llm_rate_limited", "The AI service is over its request limit. Try again in a minute.") from exc
    except (ModelTimeoutError, httpx.TimeoutException, TimeoutError) as exc:
        raise _llm_failure(exc, 504, "llm_timeout", "The AI service took too long to respond. Try again.") from exc
    except (ModelAuthenticationError, ModelPermissionDeniedError, ModelNotFoundError) as exc:
        raise _llm_failure(exc, 502, "llm_auth_failed", "The AI service rejected this server's credentials or model. This is a server configuration problem.") from exc
    except GoogleAPIError as exc:
        if exc.code == 503:  # Google's "high demand" response, which passes on its own
            raise _llm_failure(exc, 503, "llm_unavailable", "The AI service is busy right now. Try again in a moment.") from exc
        raise _llm_failure(exc, 502, "llm_error", "The AI service failed to answer. Try again.") from exc
    except (ModelError, ChatGoogleGenerativeAIError, httpx.TransportError) as exc:
        raise _llm_failure(exc, 502, "llm_error", "The AI service failed to answer. Try again.") from exc


def _llm_failure(exc: Exception, status_code: int, error: str, message: str) -> ApiError:
    logger.warning("llm call failed", extra={"error": error, "exception_type": type(exc).__name__}, exc_info=status_code == 502)
    return ApiError(status_code, error, message)


_SPEECH_SERVICES = {"stt": "speech-to-text service", "tts": "text-to-speech service"}


def speech_not_configured(service: str) -> ApiError:
    return ApiError(503, f"{service}_not_configured", f"The {_SPEECH_SERVICES[service]} is not set up on this server.")


def http_failure(service: str, exc: httpx.HTTPError) -> ApiError:
    """Maps a failed call to AssemblyAI ("stt") or Murf ("tts") to the same kinds of response the LLM errors use."""
    name = _SPEECH_SERVICES[service]
    status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
    if isinstance(exc, httpx.TimeoutException):
        error = ApiError(504, f"{service}_timeout", f"The {name} took too long to respond. Try again.")
    elif status == 429:
        error = ApiError(429, f"{service}_rate_limited", f"The {name} is over its request limit. Try again in a minute.")
    elif status in (401, 403):
        error = ApiError(502, f"{service}_auth_failed", f"The {name} rejected this server's credentials. This is a server configuration problem.")
    elif status == 402:
        error = ApiError(502, f"{service}_quota_exceeded", f"The {name} account is out of credit. This is a server problem.")
    else:
        error = ApiError(502, f"{service}_error", f"The {name} failed. Try again.")
    logger.warning(
        "speech service call failed",
        extra={"service": service, "error": error.error, "upstream_status": status},
        exc_info=error.error == f"{service}_error",
    )
    return error


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error(request: Request, exc: ApiError):
        return _response(exc.status_code, exc.error, exc.message)

    @app.exception_handler(SessionNotFound)
    async def session_not_found(request: Request, exc: SessionNotFound):
        return _response(404, "session_not_found", "Session does not exist or has expired.")

    @app.exception_handler(RateLimitExceeded)
    async def rate_limited(request: Request, exc: RateLimitExceeded):
        logger.warning("rate limit hit", extra={"limit": str(exc.limit.limit)})
        return _response(429, "rate_limited", "Too many answers submitted too quickly. Wait a moment and try again.")

    @app.exception_handler(RedisError)
    async def redis_down(request: Request, exc: RedisError):
        logger.error("redis error", exc_info=exc)
        return _response(503, "session_store_unavailable", "The session store is unavailable. Try again shortly.")

    @app.exception_handler(OperationalError)
    @app.exception_handler(InterfaceError)
    @app.exception_handler(ConnectionError)
    async def database_down(request: Request, exc: Exception):
        logger.error("database error", exc_info=exc)
        return _response(503, "database_unavailable", "The database is unavailable. Try again shortly.")

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception):
        logger.error("unhandled error", exc_info=exc)
        return _response(500, "internal_error", "Something went wrong on our side.")
