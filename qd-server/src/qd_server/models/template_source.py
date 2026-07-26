"""Template subscription models for QD2.

Subscribes to public template repositories (e.g. qd-today/templates) whose
manifest is a ``tpls_history.json`` file: {"version": "...", "har": {name: {...}}}.
"""

from datetime import datetime
from typing import Optional

from sqlmodel import Column, Field, JSON

from qd_server.models.base import BaseModel


DEFAULT_REPO_URL = (
    "https://raw.githubusercontent.com/qd-today/templates/master/tpls_history.json"
)


class TemplateSource(BaseModel, table=True):
    """A subscribed public template repository."""

    __tablename__ = "template_sources"

    # Owner (admin-managed; but keep per-user for multi-tenant flexibility)
    user_id: int = Field(foreign_key="users.id", index=True)

    name: str = Field(max_length=200)
    # URL to the manifest json (tpls_history.json format)
    url: str = Field(max_length=1000, default=DEFAULT_REPO_URL)
    enabled: bool = Field(default=True)

    # Sync state
    last_sync_at: Optional[datetime] = Field(default=None)
    manifest_version: Optional[str] = Field(default=None, max_length=50)
    template_count: int = Field(default=0)

    # Cached manifest: {name: {name, author, comments, filename, content(base64), update}}
    manifest: dict = Field(default={}, sa_column=Column(JSON))
