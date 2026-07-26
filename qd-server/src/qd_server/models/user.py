"""User model for QD2."""

from typing import Optional
from datetime import datetime

from sqlmodel import Field
from qd_server.models.base import BaseModel


class User(BaseModel, table=True):
    """User account model.

    Supports multi-user with role-based access control.
    """

    __tablename__ = "users"

    username: str = Field(unique=True, index=True, max_length=50)
    email: Optional[str] = Field(default=None, max_length=100)
    hashed_password: str = Field(max_length=200)

    # Role: admin, user
    role: str = Field(default="user", max_length=20)

    # Status
    is_active: bool = Field(default=True)
    last_login: Optional[datetime] = Field(default=None)

    # Profile
    display_name: Optional[str] = Field(default=None, max_length=100)
    avatar_url: Optional[str] = Field(default=None, max_length=500)
