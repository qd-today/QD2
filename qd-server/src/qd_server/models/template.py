"""Template model for QD2."""

from typing import Optional
import json

from sqlmodel import Field, Column, JSON
from qd_server.models.base import BaseModel


class Template(BaseModel, table=True):
    """HAR template model.

    Stores user-uploaded or created HAR templates with metadata.
    """

    __tablename__ = "templates"

    # Owner
    user_id: int = Field(foreign_key="users.id", index=True)

    # Template info
    name: str = Field(max_length=200)
    description: Optional[str] = Field(default="", max_length=1000)
    author: Optional[str] = Field(default="", max_length=100)
    version: str = Field(default="1.0", max_length=20)

    # Template data (stored as JSON)
    template_data: dict = Field(default={}, sa_column=Column(JSON))

    # Variables (stored as JSON)
    variables: dict = Field(default={}, sa_column=Column(JSON))

    # Status
    enabled: bool = Field(default=True)
    is_public: bool = Field(default=False, description="Whether template is visible to all users")

    # Tags (stored as JSON array)
    tags: list = Field(default=[], sa_column=Column(JSON))

    # Execution stats
    run_count: int = Field(default=0)
    last_run_at: Optional[str] = Field(default=None)
