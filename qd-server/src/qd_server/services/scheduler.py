"""APScheduler integration for QD2 task scheduling.

Manages scheduled task execution using APScheduler with async support.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.date import DateTrigger

logger = logging.getLogger("qd2.scheduler")


class QDScheduler:
    """QD2 task scheduler wrapping APScheduler.

    Responsibilities:
    - Load scheduled tasks from database on startup
    - Add/remove/update scheduled jobs
    - Execute task runs when triggered
    """

    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self._running = False

    async def start(self) -> None:
        """Start the scheduler and load tasks from database."""
        if self._running:
            return

        self.scheduler.start()
        self._running = True
        logger.info("Scheduler started")

        # Load existing tasks from database
        await self.load_tasks()

    async def stop(self) -> None:
        """Stop the scheduler."""
        if self._running:
            self.scheduler.shutdown(wait=False)
            self._running = False
            logger.info("Scheduler stopped")

    async def load_tasks(self) -> None:
        """Load all active tasks from database and register them."""
        from qd_server.config import get_settings
        from qd_server.models.task import Task
        from sqlmodel import select
        from sqlalchemy import not_

        settings = get_settings()
        async with settings.db.scoped_session() as session:
            result = await session.execute(
                select(Task).where(not_(Task.status.in_(["disabled", "paused"])))
            )
            tasks = result.scalars().all()

            for task in tasks:
                self._add_job(task)

            logger.info("Loaded %d scheduled tasks", len(tasks))

    def _add_job(self, task) -> None:
        """Add a single task to the scheduler based on its schedule_config."""
        job_id = f"task_{task.id}"

        # Remove existing job if any
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)

        schedule_config = task.schedule_config or {}
        schedule_type = schedule_config.get("schedule_type", "interval")

        trigger = None

        if schedule_type == "interval":
            interval = schedule_config.get("interval_seconds", 3600)
            trigger = IntervalTrigger(seconds=interval)

        elif schedule_type == "cron":
            cron_expr = schedule_config.get("cron_expression", "0 * * * *")
            # Parse simple cron: "MIN HOUR DOM MON DOW"
            parts = cron_expr.split()
            if len(parts) == 5:
                trigger = CronTrigger(
                    minute=parts[0],
                    hour=parts[1],
                    day=parts[2],
                    month=parts[3],
                    day_of_week=parts[4],
                )

        elif schedule_type == "daily":
            run_time = schedule_config.get("run_time", "00:00")
            hour, minute = run_time.split(":")
            trigger = CronTrigger(hour=int(hour), minute=int(minute))

        elif schedule_type == "once":
            run_at = schedule_config.get("run_at")
            if run_at:
                if isinstance(run_at, str):
                    run_at = datetime.fromisoformat(run_at)
                trigger = DateTrigger(run_date=run_at)

        if trigger:
            self.scheduler.add_job(
                self._execute_task,
                trigger=trigger,
                id=job_id,
                args=[task.id],
                replace_existing=True,
            )
            logger.info("Scheduled task %d: %s", task.id, schedule_type)

    def add_task(self, task) -> None:
        """Add or update a task schedule."""
        self._add_job(task)

    def remove_task(self, task_id: int) -> None:
        """Remove a task from the scheduler."""
        job_id = f"task_{task_id}"
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
            logger.info("Removed task %d from scheduler", task_id)

    async def run_task_now(self, task_id: int) -> None:
        """Immediately execute a task."""
        await self._execute_task(task_id)

    async def _execute_task(self, task_id: int) -> None:
        """Execute a scheduled task.

        This is the core execution logic that:
        1. Loads the task and its template from database
        2. Executes the template via QD Core
        3. Records the run result
        4. Sends notifications if configured
        """
        from qd_server.config import get_settings
        from qd_server.models.task import Task, TaskRun
        from qd_server.models.template import Template
        from qd_core.client.har import HARParser
        from qd_core.client.fetcher import QDFetcher
        from sqlmodel import select

        logger.info("Executing task %d", task_id)
        settings = get_settings()

        async with settings.db.scoped_session() as session:
            # Load task
            result = await session.execute(select(Task).where(Task.id == task_id))
            task = result.scalar_one_or_none()

            if task is None:
                logger.error("Task %d not found", task_id)
                return

            # Load template
            result = await session.execute(select(Template).where(Template.id == task.template_id))
            template = template_model = result.scalar_one_or_none()

            if template is None:
                logger.error("Template %d not found for task %d", task.template_id, task_id)
                return

            # Parse template data
            try:
                har_template = HARParser.parse_dict(template.template_data)
                har_template.name = template.name
                har_template.variables.update(task.variables or {})
            except Exception as e:
                logger.error("Failed to parse template %d: %s", template.id, e)
                await self._record_run(session, task, "failed", str(e))
                return

            # Execute
            fetcher = QDFetcher()
            started_at = datetime.utcnow()

            try:
                results = await fetcher.execute_template(har_template)
                finished_at = datetime.utcnow()
                duration = (finished_at - started_at).total_seconds()

                # Check if any request failed
                has_error = any(r.get("status") == "error" for r in results)
                status_str = "failed" if has_error else "success"
                error_msg = None
                if has_error:
                    error_msg = next(r.get("error") for r in results if r.get("status") == "error")

                await self._record_run(
                    session, task, status_str, error_msg,
                    started_at, finished_at, duration,
                )

                # Send notifications
                await self._send_notifications(
                    session, task.name, status_str, error_msg, duration
                )

            except Exception as e:
                finished_at = datetime.utcnow()
                duration = (finished_at - started_at).total_seconds()
                logger.error("Task %d execution failed: %s", task_id, e)
                await self._record_run(
                    session, task, "failed", str(e),
                    started_at, finished_at, duration,
                )
                await self._send_notifications(
                    session, task.name, "failed", str(e), duration
                )

    async def _record_run(
        self,
        session,
        task,
        status_str: str,
        error_message: Optional[str] = None,
        started_at: Optional[datetime] = None,
        finished_at: Optional[datetime] = None,
        duration: Optional[float] = None,
    ) -> None:
        """Record a task execution run."""
        from qd_server.models.task import TaskRun

        run = TaskRun(
            task_id=task.id,
            user_id=task.user_id,
            status=status_str,
            started_at=started_at or datetime.utcnow(),
            finished_at=finished_at,
            duration_seconds=duration,
            error_message=error_message,
        )
        session.add(run)

        task.run_count += 1
        task.last_run_at = datetime.utcnow()
        task.last_status = status_str
        session.add(task)

        await session.commit()
        logger.info("Task %d run recorded: %s", task.id, status_str)

    async def _send_notifications(
        self,
        session,
        task_name: str,
        status: str,
        error_message: Optional[str] = None,
        duration: Optional[float] = None,
    ) -> None:
        """Send notifications for task completion."""
        from qd_server.models.notification import Notification
        from qd_server.services.notification import send_notification
        from sqlmodel import select

        result = await session.execute(select(Notification).where(Notification.enabled == True))
        notifications = result.scalars().all()

        for notif in notifications:
            try:
                # Check trigger conditions
                if status == "success" and not notif.on_success:
                    continue
                if status == "failed" and not notif.on_failure:
                    continue

                config = notif.config or {}
                config["type"] = notif.notification_type

                await send_notification(
                    notification_config=config,
                    task_name=task_name,
                    status=status,
                    error_message=error_message,
                    duration_seconds=duration,
                )
            except Exception as e:
                logger.error("Failed to send notification %d: %s", notif.id, e)


# Global scheduler instance
scheduler = QDScheduler()
