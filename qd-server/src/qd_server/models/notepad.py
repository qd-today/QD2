"""Notepad model for QD2."""

from typing import Optional

from sqlmodel import Field
from qd_server.models.base import BaseModel


class Notepad(BaseModel, table=True):
    """Notepad/model for storing user notes and snippets.

    Useful for storing cookies, tokens, or other reference data.
    """

    __tablename__ = "notepads"

    # Owner
    user_id: int = Field(foreign_key="users.id", index=True)

    # Content
    title: str = Field(max_length=200)
    content: str = Field(default="", max_length=50000)
    category: Optional[str] = Field(default=None, max_length=50)

    # Tags (comma-separated)
    tags: Optional[str] = Field(default=None, max_length=500)

    # Order
    sort_order: int = Field(default=0)
