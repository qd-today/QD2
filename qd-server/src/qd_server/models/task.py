"""Task and task run models for QD2."""

from typing import Optional
from datetime import datetime

from sqlmodel import Field, Column, JSON
from qd_server.models.base import BaseModel


class Task(BaseModel, table=True):
    """Scheduled task model.

    Links a template to a schedule configuration.
    """

    __tablename__ = "tasks"

    # Owner
    user_id: int = Field(foreign_key="users.id", index=True)

    # Group
    group_id: Optional[int] = Field(default=None, foreign_key="task_groups.id", index=True)

    # Linked template
    template_id: int = Field(foreign_key="templates.id", index=True)

    # Task info
    name: str = Field(max_length=200)
    description: Optional[str] = Field(default="", max_length=1000)

    # Schedule config (stored as JSON)
    schedule_config: dict = Field(default={}, sa_column=Column(JSON))

    # Status: pending, running, success, failed, paused, disabled
    status: str = Field(default="pending", max_length=20)

    # Runtime variables override
    variables: dict = Field(default={}, sa_column=Column(JSON))

    # Persistent cookie session (original QD dump format: list of cookie dicts)
    cookie_session: list = Field(default=[], sa_column=Column(JSON))

    # Next run time
    next_run_at: Optional[datetime] = Field(default=None)

    # Execution stats
    run_count: int = Field(default=0)
    last_run_at: Optional[datetime] = Field(default=None)
    last_status: Optional[str] = Field(default=None, max_length=20)


class TaskRun(BaseModel, table=True):
    """Task execution history record."""

    __tablename__ = "task_runs"

    # References
    task_id: int = Field(foreign_key="tasks.id", index=True)
    user_id: int = Field(foreign_key="users.id", index=True)

    # Execution info
    status: str = Field(max_length=20)  # success, failed
    started_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: Optional[datetime] = Field(default=None)
    duration_seconds: Optional[float] = Field(default=None)

    # Results
    error_message: Optional[str] = Field(default=None, max_length=2000)
    response_summary: Optional[str] = Field(default=None, max_length=5000)
    extracted_variables: dict = Field(default={}, sa_column=Column(JSON))
