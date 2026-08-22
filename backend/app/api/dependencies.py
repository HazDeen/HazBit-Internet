from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated, cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import DatabaseManager
from app.integrations.redis import RedisManager


def get_database(request: Request) -> DatabaseManager:
    return cast(DatabaseManager, request.app.state.database)


def get_redis(request: Request) -> RedisManager:
    return cast(RedisManager, request.app.state.redis)


async def get_session(
    database: Annotated[DatabaseManager, Depends(get_database)],
) -> AsyncIterator[AsyncSession]:
    async with database.session() as session:
        yield session


DatabaseDependency = Annotated[DatabaseManager, Depends(get_database)]
RedisDependency = Annotated[RedisManager, Depends(get_redis)]
SessionDependency = Annotated[AsyncSession, Depends(get_session)]
