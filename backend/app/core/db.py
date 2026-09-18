from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from fastapi import Request

from app.core.config import settings


class Base(DeclarativeBase):
    pass


def create_engine_and_sessionmaker():
    engine = create_async_engine(settings.database_url)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def get_db(request: Request):
    async with request.app.state.db_sessionmaker() as db:
        yield db
