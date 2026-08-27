"""APScheduler integration for QD2 task scheduling.

Manages scheduled task execution using APScheduler with async support.
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger("qd2.scheduler")

MAX_ERROR_MESSAGE_LENGTH = 2000
MAX_RESPONSE_SUMMARY_LENGTH = 5000


def _format_task_log(value: Any) -> str:
    """Convert a QD ``__log__`` value into readable persisted text."""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def _truncate_log(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    suffix = "\n... (truncated)"
    return value[: max_length - len(suffix)] + suffix


def _format_task_failure(
    results: list[dict[str, Any]],
    total_requests: int,
    error_message: str | None,
) -> str | None:
    for result_index, result in enumerate(results):
        if result.get("status") != "error" and result.get("success") is not False:
            continue
        reason = result.get("message") or result.get("error") or error_message
        parts = [f"Failed at {result_index + 1}/{max(total_requests, 1)} request"]
        if reason:
            parts.append(str(reason))
        if result.get("url"):
            parts.append(f"Request URL: {result['url']}")
        return _truncate_log(",".join(parts), MAX_ERROR_MESSAGE_LENGTH)
    return _truncate_log(error_message, MAX_ERROR_MESSAGE_LENGTH) if error_message else None


class QDScheduler:
    """QD2 task scheduler wrapping APScheduler.

    Responsibilities:
    - Load scheduled tasks from database on startup
    - Add/remove/update scheduled jobs
    - Execute task runs when triggered
    """

    def __init__(self, max_concurrent_tasks: int | None = None):
        if max_concurrent_tasks is None:
            from qd_server.config import get_settings

            max_concurrent_tasks = getattr(get_settings(), "max_concurrent_tasks", 5)
        if max_concurrent_tasks < 1:
            raise ValueError("max_concurrent_tasks must be at least 1")

        self.scheduler = AsyncIOScheduler()
        self._running = False
        self.max_concurrent_tasks = max_concurrent_tasks
        self._execution_semaphore = asyncio.Semaphore(max_concurrent_tasks)

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
        from sqlalchemy import not_
        from sqlmodel import select

        from qd_server.config import get_settings
        from qd_server.models.task import Task
        from qd_server.models.template import Template
        from qd_server.models.user import User

        settings = get_settings()
        async with settings.db.scoped_session() as session:
            result = await session.execute(
                select(Task)
                .join(User, User.id == Task.user_id)
                .join(Template, Template.id == Task.template_id)
                .where(
                    not_(Task.status.in_(["disabled", "paused"])),
                    User.is_active,
                    Template.enabled,
                    Template.user_id == Task.user_id,
                )
            )
            tasks = result.scalars().all()

            for task in tasks:
                try:
                    self._add_job(task)
                except Exception:
                    logger.exception("Failed to schedule task %d", task.id)

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
            parsed_time = None
            for time_format in ("%H:%M:%S", "%H:%M"):
                try:
                    parsed_time = datetime.strptime(run_time, time_format)
                    break
                except (TypeError, ValueError):
                    continue
            if parsed_time is None:
                logger.error("Task %d has invalid daily run_time: %r", task.id, run_time)
                return
            start_date = schedule_config.get("start_date")
            if isinstance(start_date, str) and start_date:
                start_date = datetime.fromisoformat(start_date)
            trigger = CronTrigger(
                hour=parsed_time.hour,
                minute=parsed_time.minute,
                second=parsed_time.second,
                start_date=start_date or None,
            )

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

    def get_next_run_time(self, task_id: int) -> datetime | None:
        """Return APScheduler's current next fire time for a task."""
        job = self.scheduler.get_job(f"task_{task_id}")
        return getattr(job, "next_run_time", None) if job is not None else None

    async def run_task_now(self, task_id: int) -> Any | None:
        """Immediately execute a task (manual trigger skips random delay)."""
        return await self._execute_task(task_id, manual=True)

    async def _execute_task(self, task_id: int, manual: bool = False) -> Any | None:
        """Execute a task after waiting for a global concurrency slot."""
        async with self._execution_semaphore:
            return await self._execute_task_impl(task_id, manual)

    async def _execute_task_impl(self, task_id: int, manual: bool = False) -> Any | None:
        """Execute a scheduled task.

        This is the core execution logic that:
        1. Loads the task and its template from database
        2. Executes the template via QD Core
        3. Records the run result
        4. Sends notifications if configured
        """
        from qd_core.client.cookie_session import CookieSession
        from qd_core.client.fetcher import QDFetcher
        from qd_core.client.har import HARParser
        from sqlmodel import select

        from qd_server.config import get_settings
        from qd_server.models.task import Task
        from qd_server.models.template import Template
        from qd_server.models.user import User
        from qd_server.services.encryption import protect_list, unprotect_dict, unprotect_list

        logger.info("Executing task %d", task_id)
        settings = get_settings()
        api_base_url = f"http://127.0.0.1:{getattr(settings, 'port', 8923)}"

        from qd_server.services.log_stream import log_stream

        async with settings.db.scoped_session() as session:
            # Load task
            result = await session.execute(
                select(Task)
                .join(User, User.id == Task.user_id)
                .where(Task.id == task_id, User.is_active)
            )
            task = result.scalar_one_or_none()

            if task is None:
                logger.error("Task %d not found or user is disabled", task_id)
                return None
            if not manual and task.status in ("disabled", "paused"):
                logger.info("Skipping inactive scheduled task %d", task_id)
                return None

            # Execution options: retry / random delay / proxy
            exec_cfg = task.execution_config or {}
            delay_min = max(0, int(exec_cfg.get("random_delay_min", 0) or 0))
            delay_max = max(delay_min, int(exec_cfg.get("random_delay_max", 0) or 0))

            # End the read transaction before a potentially long delay.
            await session.commit()

            # Random pre-execution delay (avoid fixed-time detection)
            if delay_max > 0 and not manual:
                import random as _random

                delay = _random.uniform(delay_min, delay_max)
                logger.info("Task %d random delay %.1fs before run", task_id, delay)
                await asyncio.sleep(delay)

            # State may have changed during the delay. Reload task and template
            # before doing network work, while keeping manual runs available for
            # paused tasks owned by an active user.
            result = await session.execute(
                select(Task)
                .join(User, User.id == Task.user_id)
                .where(Task.id == task_id, User.is_active)
            )
            task = result.scalar_one_or_none()
            if task is None or (not manual and task.status in ("disabled", "paused")):
                logger.info("Task %d became inactive before execution", task_id)
                await session.commit()
                return None

            result = await session.execute(
                select(Template).where(
                    Template.id == task.template_id,
                    Template.user_id == task.user_id,
                    Template.enabled,
                )
            )
            template = result.scalar_one_or_none()
            if template is None:
                logger.error("Template %d not found for task %d", task.template_id, task_id)
                await session.commit()
                return None

            await session.commit()

            # Parse template data
            try:
                har_template = HARParser.parse_dict(template.template_data)
                har_template.name = template.name
                har_template.variables.update(unprotect_dict(task.variables, "task.variables"))
            except Exception as e:
                logger.error("Failed to parse template %d: %s", template.id, e)
                return await self._record_run(session, task, "failed", str(e))

            # Restore persistent cookie session for this task
            cookie_session = CookieSession().from_json(
                unprotect_list(task.cookie_session, "task.cookie_session")
            )

            # Apply the latest retry/proxy settings after the state reload.
            exec_cfg = task.execution_config or {}
            retry_count = max(0, int(exec_cfg.get("retry_count", 0) or 0))
            retry_interval = max(0, int(exec_cfg.get("retry_interval_seconds", 30) or 30))
            proxy = (exec_cfg.get("proxy") or "").strip() or None

            started_at = datetime.utcnow()
            task_timeout = getattr(settings, "task_timeout", 900)
            task_request_limit = getattr(settings, "task_request_limit", 1500)
            deadline = time.monotonic() + task_timeout
            log_stream.publish(
                task.user_id, "task_start", task_id=task_id, task_name=task.name,
                attempts=retry_count + 1,
            )

            results = []
            error_msg = None
            status_str = "failed"
            task_log = None
            requests_executed = 0
            enabled_request_count = sum(1 for request in har_template.requests if request.checked)
            for attempt in range(retry_count + 1):
                remaining_request_limit = task_request_limit - requests_executed
                if remaining_request_limit <= 0:
                    error_msg = f"Task request limit exceeded ({task_request_limit})"
                    break
                # Fresh fetcher per attempt, reusing the same cookie session
                fetcher = QDFetcher(
                    cookie_session=cookie_session,
                    proxy=proxy,
                    api_base_url=api_base_url,
                )
                if hasattr(fetcher, "request_limit"):
                    fetcher.request_limit = remaining_request_limit
                if attempt > 0:
                    log_stream.publish(
                        task.user_id, "task_retry", task_id=task_id, task_name=task.name,
                        attempt=attempt + 1,
                    )
                try:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise asyncio.TimeoutError
                    results = await asyncio.wait_for(
                        fetcher.execute_template(har_template),
                        timeout=remaining,
                    )
                    for idx, r in enumerate(results):
                        request_index = r.get("request_index", idx)
                        log_stream.publish(
                            task.user_id, "request_done", task_id=task_id, task_name=task.name,
                            request_index=request_index,
                            success=bool(r.get("success", r.get("status") != "error")),
                            status_code=r.get("status_code"), url=r.get("url", ""),
                            message=(r.get("message") or r.get("error") or "")[:200],
                        )
                        extracted = r.get("extracted_variables") or {}
                        if "__log__" in extracted:
                            task_log = _format_task_log(extracted["__log__"])
                            log_stream.publish(
                                task.user_id, "task_log", task_id=task_id, task_name=task.name,
                                request_index=request_index, content=task_log,
                            )
                    has_error = any(r.get("status") == "error" for r in results)
                    has_assert_fail = any(r.get("success") is False for r in results)
                    if not has_error and not has_assert_fail:
                        status_str = "success"
                        error_msg = None
                        break
                    # collect failure reason
                    if has_error:
                        error_msg = next(r.get("error") for r in results if r.get("status") == "error")
                    else:
                        error_msg = next(
                            (r.get("message") for r in results if r.get("success") is False and r.get("message")),
                            "assert failed",
                        )
                    error_msg = _format_task_failure(
                        results,
                        enabled_request_count,
                        error_msg,
                    )
                except asyncio.TimeoutError:
                    error_msg = f"Task execution exceeded {task_timeout} seconds"
                    break
                except Exception as e:
                    error_msg = str(e)
                finally:
                    requests_executed += getattr(fetcher, "request_count", len(results))

                if attempt < retry_count:
                    logger.warning(
                        "Task %d attempt %d/%d failed (%s), retrying in %ds",
                        task_id, attempt + 1, retry_count + 1, error_msg, retry_interval,
                    )
                    remaining = deadline - time.monotonic()
                    if remaining <= retry_interval:
                        error_msg = f"Task execution exceeded {task_timeout} seconds"
                        break
                    await asyncio.sleep(retry_interval)

            finished_at = datetime.utcnow()
            duration = (finished_at - started_at).total_seconds()

            # Persist updated cookies back onto the task
            try:
                task.cookie_session = protect_list(
                    fetcher.session.to_json(),
                    "task.cookie_session",
                )
            except Exception as ce:
                logger.warning("Failed to serialize cookie session for task %d: %s", task_id, ce)

            run = await self._record_run(
                session, task, status_str, error_msg,
                started_at, finished_at, duration,
                response_summary=task_log if status_str == "success" else None,
                extracted_variables={"__log__": task_log} if task_log is not None else {},
            )

            log_stream.publish(
                task.user_id, "task_finish", task_id=task_id, task_name=task.name,
                status=status_str, duration=round(duration, 2),
                error=(error_msg or "")[:300],
            )

            # Send notifications
            await self._send_notifications(
                session,
                task.id,
                task.user_id,
                task.name,
                status_str,
                error_msg,
                duration,
                execution_config=task.execution_config,
                task_log=task_log,
            )
            return run

    async def _record_run(
        self,
        session,
        task,
        status_str: str,
        error_message: str | None = None,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
        duration: float | None = None,
        response_summary: str | None = None,
        extracted_variables: dict[str, Any] | None = None,
    ) -> Any:
        """Record a task execution run."""
        from qd_server.models.task import TaskRun

        run = TaskRun(
            task_id=task.id,
            user_id=task.user_id,
            status=status_str,
            started_at=started_at or datetime.utcnow(),
            finished_at=finished_at,
            duration_seconds=duration,
            error_message=(
                _truncate_log(error_message, MAX_ERROR_MESSAGE_LENGTH)
                if error_message
                else None
            ),
            response_summary=(
                _truncate_log(response_summary, MAX_RESPONSE_SUMMARY_LENGTH)
                if response_summary
                else None
            ),
            extracted_variables=extracted_variables or {},
        )
        session.add(run)

        task.run_count += 1
        task.last_run_at = datetime.utcnow()
        task.last_status = status_str
        session.add(task)

        await session.commit()
        logger.info("Task %d run recorded: %s", task.id, status_str)
        return run

    async def _send_notifications(
        self,
        session,
        task_id: int,
        user_id: int,
        task_name: str,
        status: str,
        error_message: str | None = None,
        duration: float | None = None,
        execution_config: dict | None = None,
        task_log: str | None = None,
    ) -> None:
        """Send notifications for task completion."""
        from sqlalchemy import or_
        from sqlmodel import select

        from qd_server.models.notification import Notification
        from qd_server.models.task import TaskRun
        from qd_server.services.encryption import unprotect_dict
        from qd_server.services.notification import send_notification

        execution_config = execution_config or {}
        if status == "success" and execution_config.get("notify_on_success", True) is False:
            return
        if status == "failed" and execution_config.get("notify_on_failure", True) is False:
            return

        result = await session.execute(
            select(Notification).where(
                Notification.user_id == user_id,
                Notification.enabled,
                or_(Notification.task_id.is_(None), Notification.task_id == task_id),
            )
        )
        notifications = result.scalars().all()

        consecutive_failures = 0
        if status == "failed" and notifications:
            run_result = await session.execute(
                select(TaskRun.status)
                .where(TaskRun.task_id == task_id)
                .order_by(TaskRun.id.desc())
                .limit(100)
            )
            for run_status in run_result.scalars().all():
                if run_status != "failed":
                    break
                consecutive_failures += 1

        for notif in notifications:
            try:
                # Check trigger conditions
                if status == "success" and not notif.on_success:
                    continue
                if status == "failed" and not notif.on_failure:
                    continue

                config = unprotect_dict(notif.config, "notification.config")
                if status == "failed":
                    try:
                        failure_threshold = int(config.get("failure_threshold", 1) or 1)
                    except (TypeError, ValueError):
                        failure_threshold = 1
                    failure_threshold = min(max(failure_threshold, 1), 100)
                    if consecutive_failures < failure_threshold:
                        continue
                config["type"] = notif.notification_type

                await send_notification(
                    notification_config=config,
                    task_name=task_name,
                    status=status,
                    error_message=error_message,
                    duration_seconds=duration,
                    task_log=task_log,
                )
            except Exception as e:
                logger.error("Failed to send notification %d: %s", notif.id, e)


# Global scheduler instance
scheduler = QDScheduler()
