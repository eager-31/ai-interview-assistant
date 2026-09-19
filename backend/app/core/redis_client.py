from fastapi import Request
from redis.asyncio import Redis

from app.core.config import settings


# redis-py gives up after 5 seconds by default. On a slow or lossy connection a few
# dropped packets take longer than that to recover from, and every request would fail.
CONNECT_TIMEOUT_SECONDS = 15


def create_redis() -> Redis:
    return Redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=CONNECT_TIMEOUT_SECONDS)


async def get_redis(request: Request) -> Redis:
    return request.app.state.redis
