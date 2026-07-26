"""QD Server configuration settings.

Extends QDCoreSettings with server-specific settings including
database, JWT authentication, and scheduler configuration.
"""

from asyncio import current_task
from enum import Enum
from functools import cached_property, lru_cache
from pathlib import Path
from typing import Optional, Union, cast
from urllib.parse import ParseResult, urlencode, urlparse

from pydantic import Field, ValidationInfo, field_validator, model_validator
from qd_core.config import QDCoreSettings
from sqlalchemy.ext.asyncio import async_scoped_session, async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession


class DBType(Enum):
    """Database type enum."""

    mysql = "mysql"
    sqlite3 = "sqlite3"


class Sqlite3Settings(QDCoreSettings):
    """SQLite3 settings."""

    db_path: Path = Field(
        default_factory=lambda: Path.home() / ".qd2" / "database.db",
        description="SQLite3 database path",
    )
    db_schema: str = Field(default="sqlite", frozen=True)
    driver: str = Field(default="aiosqlite")

    @property
    def engine_url(self) -> str:
        return f"{self.db_schema}+{self.driver}:///{self.db_path}"


class MysqlSettings(QDCoreSettings):
    """MySQL settings."""

    url: Optional[str] = Field(default=None, alias="QD_MYSQL_URL")
    db_schema: str = Field(default="mysql", frozen=True)
    driver: str = Field(default="aiomysql")
    hostname: str = Field(default="localhost")
    port: int = Field(default=3306)
    database: str = Field(default="qd")
    username: str = Field(default="qd")
    password: str = Field(default="")
    auth_plugin: str = Field(default="mysql_native_password")

    @model_validator(mode="after")
    def update_fields_from_url(self) -> "MysqlSettings":
        if self.url:
            parsed = urlparse(self.url)
            self.db_schema = parsed.scheme or self.db_schema
            self.hostname = parsed.hostname or self.hostname
            self.port = parsed.port or self.port
            self.database = (parsed.path[1:] if parsed.path and len(parsed.path) > 1 else "") or self.database
            self.username = parsed.username or self.username
            self.password = parsed.password or self.password
        return self

    @property
    def engine_url(self) -> str:
        password_part = f":{self.password}" if self.password else ""
        return f"{self.db_schema}+{self.driver}://{self.username}{password_part}@{self.hostname}:{self.port}/{self.database}"


class JWTSettings(QDCoreSettings):
    """JWT authentication settings."""

    secret_key: str = Field(
        default="change-me-in-production",
        alias="QD_JWT_SECRET",
        description="JWT signing secret key",
    )
    algorithm: str = Field(default="HS256")
    access_token_expire_minutes: int = Field(default=15, description="Access token TTL in minutes")
    refresh_token_expire_days: int = Field(default=7, description="Refresh token TTL in days")


class DBSettings(QDCoreSettings):
    """Database settings."""

    db_type: DBType = Field(default=DBType.sqlite3)
    engine_settings: Union[MysqlSettings, Sqlite3Settings] = Field(default_factory=Sqlite3Settings)
    logging_name: str = Field(default="QD.SQL")
    logging_level: str = Field(default="WARNING")
    max_overflow: int = Field(default=50)
    pool_size: int = Field(default=10)

    @field_validator("engine_settings", mode="after")
    @classmethod
    def validate_engine_settings(cls, value, info: ValidationInfo):
        db_type = info.data.get("db_type")
        if db_type == DBType.sqlite3 and not isinstance(value, Sqlite3Settings):
            raise ValueError("SQLite3 settings required for sqlite3 database type")
        elif db_type == DBType.mysql and not isinstance(value, MysqlSettings):
            raise ValueError("MySQL settings required for mysql database type")
        return value

    @cached_property
    def engine(self):
        if self.db_type == DBType.sqlite3:
            settings = cast(Sqlite3Settings, self.engine_settings)
            return create_async_engine(
                settings.engine_url,
                logging_name=self.logging_name,
                pool_pre_ping=True,
            )
        elif self.db_type == DBType.mysql:
            settings = cast(MysqlSettings, self.engine_settings)
            return create_async_engine(
                settings.engine_url,
                logging_name=self.logging_name,
                pool_size=self.pool_size,
                max_overflow=self.max_overflow,
                pool_pre_ping=True,
            )
        raise ValueError(f"Unsupported database type: {self.db_type}")

    @cached_property
    def scoped_session(self):
        return async_scoped_session(
            async_sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False),
            scopefunc=current_task,
        )


class QDServerSettings(QDCoreSettings):
    """QD Server settings combining core, database, and JWT."""

    db: DBSettings = Field(default_factory=DBSettings)
    jwt: JWTSettings = Field(default_factory=JWTSettings)

    # Server
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8924)
    reload: bool = Field(default=False)


@lru_cache
def get_settings() -> QDServerSettings:
    """Get cached server settings."""
    return QDServerSettings()
