import asyncio
from datetime import datetime, timedelta, timezone
from uuid import UUID

import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_db
from app.models import User

ALGORITHM = "HS256"
BCRYPT_MAX_BYTES = 72

bearer = HTTPBearer(auto_error=False)


def _unauthorized(message: str) -> HTTPException:
    return HTTPException(
        status_code=401,
        detail={"error": "unauthorized", "message": message},
        headers={"WWW-Authenticate": "Bearer"},
    )


# bcrypt is deliberately slow (that is the point), so it runs in a thread
# instead of blocking the event loop for every other request.
async def hash_password(password: str) -> str:
    hashed = await asyncio.to_thread(bcrypt.hashpw, password.encode(), bcrypt.gensalt())
    return hashed.decode()


async def verify_password(password: str, hashed: str) -> bool:
    encoded = password.encode()
    if len(encoded) > BCRYPT_MAX_BYTES:
        return False  # registration rejects these, so no stored hash can match
    return await asyncio.to_thread(bcrypt.checkpw, encoded, hashed.encode())


def create_access_token(user_id: UUID) -> str:
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    return jwt.encode({"sub": str(user_id), "exp": expires}, settings.jwt_secret, algorithm=ALGORITHM)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None:
        raise _unauthorized("Missing bearer token.")
    try:
        # "require" rejects tokens that omit exp, which would otherwise never expire.
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=[ALGORITHM],
            options={"require": ["exp", "sub"]},
        )
        user_id = UUID(payload["sub"])
    except jwt.ExpiredSignatureError:
        raise _unauthorized("Token has expired.")
    except (jwt.InvalidTokenError, ValueError):
        raise _unauthorized("Invalid token.")

    user = await db.get(User, user_id)
    if user is None:
        raise _unauthorized("Invalid token.")
    return user
