"""Base model and database session utilities."""

import contextlib
from typing import AsyncIterator, Optional
from datetime import datetime

from sqlmodel import Field, SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from qd_server.config import get_settings


class TimestampMixin:
    """Mixin that adds created_at and updated_at timestamps."""

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class BaseModel(SQLModel):
    """Base model with common fields for all QD2 database models.

    Subclasses must set table=True to be registered as database tables.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class AlchemyMixin:
    """Mixin providing async database session management."""

    @property
    def sql_session(self):
        return get_settings().db.scoped_session()

    @contextlib.asynccontextmanager
    async def transaction(self, sql_session: Optional[AsyncSession] = None) -> AsyncIterator[AsyncSession]:
        try:
            if sql_session is None:
                async with self.sql_session as sql_session:
                    async with sql_session.begin():
                        yield sql_session
            elif not sql_session.in_transaction():
                async with sql_session.begin():
                    yield sql_session
            else:
                yield sql_session
        finally:
            get_settings().db.scoped_session.remove()
