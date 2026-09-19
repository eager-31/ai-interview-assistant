from datetime import datetime, timezone
from uuid import UUID

from redis.asyncio import Redis

# The LangGraph checkpointer TTL in main.py is derived from this, otherwise
# agent state and session metadata would expire at different times.
SESSION_TTL_SECONDS = 2 * 60 * 60


class SessionNotFound(Exception):
    pass


def _key(session_id: UUID) -> str:
    return f"session:{session_id}"


async def create_session(redis: Redis, session_id: UUID, user_id: UUID, subject: str, message: str) -> None:
    key = _key(session_id)
    await redis.hset(
        key,
        mapping={
            "user_id": str(user_id),
            "subject": subject,
            "status": "in_progress",
            "question_number": 1,
            # What the interviewer last said; the speech endpoint reads this aloud.
            "last_message": message,
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    await redis.expire(key, SESSION_TTL_SECONDS)


async def get_session(redis: Redis, session_id: UUID, user_id: UUID) -> dict[str, str]:
    session = await redis.hgetall(_key(session_id))
    # Someone else's session looks exactly like a missing one, so ids can't be probed.
    if not session or session["user_id"] != str(user_id):
        raise SessionNotFound(str(session_id))
    return session


async def advance_question(redis: Redis, session_id: UUID, message: str) -> int:
    key = _key(session_id)
    async with redis.pipeline() as pipe:
        pipe.hincrby(key, "question_number", 1)
        pipe.hset(key, "last_message", message)
        question_number, _ = await pipe.execute()
    return question_number


async def mark_completed(redis: Redis, session_id: UUID, message: str) -> None:
    await redis.hset(_key(session_id), mapping={"status": "completed", "last_message": message})
