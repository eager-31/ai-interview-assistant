import jwt
from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings
from app.core.security import ALGORITHM


def rate_limit_key(request: Request) -> str:
    """Limit per logged-in user, so one person on a shared network doesn't use up everyone's allowance."""
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        try:
            payload = jwt.decode(header[7:], settings.jwt_secret, algorithms=[ALGORITHM])
            if payload.get("sub"):
                return f"user:{payload['sub']}"
        except jwt.InvalidTokenError:
            pass
    return get_remote_address(request)


# Counters are kept in this process's memory. That is exact for a single
# instance; with several instances each would count separately. A Redis-backed
# store would fix that, but slowapi's Redis storage is synchronous and would
# block the event loop on every request.
limiter = Limiter(key_func=rate_limit_key)
