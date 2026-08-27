"""QD Server configuration settings.

Extends QDCoreSettings with server-specific settings including
database, JWT authentication, and scheduler configuration.
"""

import os
import secrets
from asyncio import current_task
from enum import Enum
from functools import cached_property, lru_cache
from pathlib import Path
from typing import Optional, Union, cast
from urllib.parse import urlparse

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


DEFAULT_JWT_SECRET = "change-me-in-production"
DEFAULT_ENCRYPTION_KEY = "binux"


class JWTSettings(QDCoreSettings):
    """JWT authentication settings."""

    secret_key: str = Field(
        default=DEFAULT_JWT_SECRET,
        alias="QD_JWT_SECRET",
        description="JWT signing secret key",
    )
    algorithm: str = Field(default="HS256")
    access_token_expire_minutes: int = Field(default=15, description="Access token TTL in minutes")
    refresh_token_expire_days: int = Field(default=7, description="Refresh token TTL in days")


class SMTPSettings(QDCoreSettings):
    """Global SMTP transport defaults used by email notification channels."""

    ssl: bool = Field(default=False, alias="QD_SMTP_SSL")
    starttls: bool = Field(default=True, alias="QD_SMTP_STARTTLS")


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
    smtp: SMTPSettings = Field(default_factory=SMTPSettings)

    # Server
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8923)
    reload: bool = Field(default=False)
    max_concurrent_tasks: int = Field(
        default=5,
        ge=1,
        description="Maximum number of task runs executing concurrently per server process",
    )
    task_timeout: int = Field(
        default=900,
        ge=1,
        description="Maximum execution time in seconds for one task run",
    )
    encryption_key: str = Field(
        default=DEFAULT_ENCRYPTION_KEY,
        description="Key used to encrypt sensitive database fields",
    )
    login_rate_limit: int = Field(
        default=10,
        ge=0,
        description="Failed login attempts allowed per username and client IP; 0 disables",
    )
    login_rate_limit_window_seconds: int = Field(default=3600, ge=1)
    public_url: str = Field(
        default="",
        description="Externally reachable base URL used in generated links",
    )
    ws_ping_interval: int = Field(default=5, ge=1)
    ws_ping_timeout: int = Field(default=30, ge=1)
    ws_max_queue_size: int = Field(default=100, ge=1)
    ws_max_connections: int = Field(default=30, ge=1)

    @field_validator("public_url")
    @classmethod
    def validate_public_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if value and urlparse(value).scheme not in {"http", "https"}:
            raise ValueError("public_url must use http or https")
        return value


def ensure_jwt_secret(settings: QDServerSettings) -> None:
    """Replace the insecure development default with a persistent random key."""
    if settings.jwt.secret_key != DEFAULT_JWT_SECRET:
        return

    settings.ensure_config_dir()
    secret_path = settings.config_dir / "jwt-secret"
    try:
        descriptor = os.open(secret_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        secret = secret_path.read_text(encoding="ascii").strip()
    else:
        secret = secrets.token_urlsafe(48)
        with os.fdopen(descriptor, "w", encoding="ascii") as secret_file:
            secret_file.write(secret)
    if len(secret) < 32:
        raise RuntimeError(f"JWT secret file is invalid: {secret_path}")
    settings.jwt.secret_key = secret


def ensure_encryption_key(settings: QDServerSettings) -> None:
    """Apply the fixed default when no explicit encryption key is configured."""
    if not settings.encryption_key:
        settings.encryption_key = DEFAULT_ENCRYPTION_KEY


@lru_cache
def get_settings() -> QDServerSettings:
    """Get cached server settings."""
    return QDServerSettings()
