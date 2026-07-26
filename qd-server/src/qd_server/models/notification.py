"""Notification model for QD2."""

from typing import Optional

from sqlmodel import Field, Column, JSON
from qd_server.models.base import BaseModel


class Notification(BaseModel, table=True):
    """Notification configuration model.

    Stores webhook or email notification settings linked to tasks.
    """

    __tablename__ = "notifications"

    # Owner
    user_id: int = Field(foreign_key="users.id", index=True)

    # Linked task (optional, None means global notification)
    task_id: Optional[int] = Field(default=None, foreign_key="tasks.id", index=True)

    # Notification info
    name: str = Field(max_length=100)
    notification_type: str = Field(max_length=20)  # webhook, email
    enabled: bool = Field(default=True)

    # Config (stored as JSON - contains webhook_url, email settings, etc.)
    config: dict = Field(default={}, sa_column=Column(JSON))

    # Trigger conditions
    on_success: bool = Field(default=True)
    on_failure: bool = Field(default=True)
