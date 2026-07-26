"""System settings model — key/value store for global config (e.g. registration switch)."""

from sqlmodel import Column, Field, JSON

from qd_server.models.base import BaseModel


class SystemSetting(BaseModel, table=True):
    """Global system settings as key/value pairs."""

    __tablename__ = "system_settings"

    key: str = Field(unique=True, index=True, max_length=100)
    value: dict = Field(default={}, sa_column=Column(JSON))
