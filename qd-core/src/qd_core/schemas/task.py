"""Task and scheduling schemas for QD2."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    """Status of a scheduled task."""

    PENDING = "pending"          # Waiting to run
    RUNNING = "running"          # Currently executing
    SUCCESS = "success"          # Last run succeeded
    FAILED = "failed"            # Last run failed
    PAUSED = "paused"            # Paused by user
    DISABLED = "disabled"        # Disabled (not scheduled)


class ScheduleType(str, Enum):
    """Type of scheduling."""

    ONCE = "once"                # Run once at specified time
    CRON = "cron"                # Cron expression
    INTERVAL = "interval"        # Fixed interval (seconds)
    DAILY = "daily"              # Run daily at specified time
    WEEKLY = "weekly"            # Run weekly on specified days


class ScheduleConfig(BaseModel):
    """Scheduling configuration for a task."""

    schedule_type: ScheduleType = ScheduleType.INTERVAL

    # For interval-based scheduling
    interval_seconds: Optional[int] = Field(
        default=None,
        ge=1,
        description="Interval in seconds between runs",
    )

    # For cron-based scheduling
    cron_expression: Optional[str] = Field(
        default=None,
        description="Cron expression (e.g. '0 9 * * 1-5')",
    )

    # For daily/weekly scheduling
    run_time: Optional[str] = Field(
        default=None,
        description="Time to run in HH:MM format",
    )
    run_days: Optional[list[int]] = Field(
        default=None,
        description="Days of week (0=Monday, 6=Sunday)",
    )

    # For one-time scheduling
    run_at: Optional[datetime] = Field(
        default=None,
        description="Specific datetime to run once",
    )

    # Execution window
    start_time: Optional[datetime] = Field(default=None, description="Schedule start time")
    end_time: Optional[datetime] = Field(default=None, description="Schedule end time")


class TaskRunResult(BaseModel):
    """Result of a single task execution."""

    task_id: str
    status: TaskStatus
    started_at: datetime
    finished_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    error_message: Optional[str] = None
    response_summary: Optional[str] = None
    extracted_variables: dict[str, Any] = Field(default_factory=dict)


class NotificationType(str, Enum):
    """Types of notifications supported."""

    WEBHOOK = "webhook"
    EMAIL = "email"


class NotificationConfig(BaseModel):
    """Configuration for task notifications."""

    notification_type: NotificationType
    enabled: bool = True

    # For webhook
    webhook_url: Optional[str] = None
    webhook_method: str = "POST"
    webhook_headers: dict[str, str] = Field(default_factory=dict)

    # For email
    email_to: Optional[str] = None
    email_smtp_host: Optional[str] = None
    email_smtp_port: int = 587
    email_smtp_user: Optional[str] = None
    email_smtp_password: Optional[str] = None

    # Trigger conditions
    on_success: bool = True
    on_failure: bool = True
