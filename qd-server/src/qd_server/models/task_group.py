"""Task group model for QD2."""

from typing import Optional

from sqlmodel import Field
from qd_server.models.base import BaseModel


class TaskGroup(BaseModel, table=True):
    """Task group model for organizing tasks."""

    __tablename__ = "task_groups"

    # Owner
    user_id: int = Field(foreign_key="users.id", index=True)

    # Group info
    name: str = Field(max_length=100)
    description: Optional[str] = Field(default="", max_length=500)
    sort_order: int = Field(default=0)
    color: Optional[str] = Field(default=None, max_length=20, description="Group color for UI")
