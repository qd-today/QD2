"""Scheduler compatibility and notification isolation tests."""

import asyncio
from datetime import datetime
from types import SimpleNamespace

import pytest
import qd_server.models  # noqa: F401 - register all tables
from qd_server.config import QDServerSettings
from qd_server.models.notification import Notification
from qd_server.models.task import Task, TaskRun
from qd_server.models.template import Template
from qd_server.models.user import User
from qd_server.services.scheduler import QDScheduler, _format_task_failure
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession


class SchedulerCapture:
    def __init__(self):
        self.job = None

    def get_job(self, _job_id):
        return None

    def add_job(self, func, **kwargs):
        self.job = (func, kwargs)


def test_max_concurrent_tasks_can_be_configured_from_environment(monkeypatch):
    monkeypatch.delenv("QD_MAX_CONCURRENT_TASKS", raising=False)
    assert QDServerSettings(_env_file=None).max_concurrent_tasks == 5

    monkeypatch.setenv("QD_MAX_CONCURRENT_TASKS", "9")
    assert QDServerSettings(_env_file=None).max_concurrent_tasks == 9


@pytest.mark.asyncio
async def test_task_execution_respects_global_concurrency_limit(monkeypatch):
    service = QDScheduler(max_concurrent_tasks=2)
    active = 0
    peak = 0
    limit_reached = asyncio.Event()
    release = asyncio.Event()

    async def fake_execute(task_id, manual=False):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        if active == 2:
            limit_reached.set()
        try:
            await release.wait()
            return task_id, manual
        finally:
            active -= 1

    monkeypatch.setattr(service, "_execute_task_impl", fake_execute)
    runs = [asyncio.create_task(service._execute_task(task_id)) for task_id in range(5)]

    await asyncio.wait_for(limit_reached.wait(), timeout=1)
    await asyncio.sleep(0)
    assert active == 2
    assert peak == 2

    release.set()
    assert await asyncio.gather(*runs) == [(task_id, False) for task_id in range(5)]
    assert peak == 2


def test_daily_schedule_preserves_seconds():
    service = QDScheduler()
    capture = SchedulerCapture()
    service.scheduler = capture
    task = SimpleNamespace(
        id=7,
        schedule_config={"schedule_type": "daily", "run_time": "08:30:15"},
    )
    service._add_job(task)
    trigger = capture.job[1]["trigger"]
    next_run = trigger.get_next_fire_time(None, datetime(2026, 1, 1, 8, 30, 0))
    assert (next_run.hour, next_run.minute, next_run.second) == (8, 30, 15)


def test_daily_schedule_preserves_start_date():
    service = QDScheduler()
    capture = SchedulerCapture()
    service.scheduler = capture
    task = SimpleNamespace(
        id=8,
        schedule_config={
            "schedule_type": "daily",
            "run_time": "00:50:10",
            "start_date": "2026-08-25",
        },
    )

    service._add_job(task)

    trigger = capture.job[1]["trigger"]
    assert trigger.start_date.date().isoformat() == "2026-08-25"


def test_next_run_time_reads_registered_job():
    expected = datetime(2026, 3, 4, 5, 6, 7)
    service = QDScheduler()
    service.scheduler = SimpleNamespace(
        get_job=lambda job_id: SimpleNamespace(next_run_time=expected)
        if job_id == "task_7"
        else None
    )

    assert service.get_next_run_time(7) == expected
    assert service.get_next_run_time(8) is None


def test_failure_log_matches_qd_v1_format():
    message = _format_task_failure(
        [
            {
                "status": "failed",
                "success": False,
                "message": (
                    'Fail assert: {"re": "200", "from": "status"} from success_asserts,'
                    "Response Error : HTTP 403: Forbidden"
                ),
                "url": "https://example.test/account",
            }
        ],
        2,
        "login required",
    )

    assert message == (
        'Failed at 1/2 request,Fail assert: {"re": "200", "from": "status"} '
        "from success_asserts,Response Error : HTTP 403: Forbidden,"
        "Request URL: https://example.test/account"
    )


@pytest.mark.asyncio
async def test_notifications_are_scoped_to_user_and_task(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    sent = []

    async def fake_send(**kwargs):
        sent.append(kwargs)

    monkeypatch.setattr("qd_server.services.notification.send_notification", fake_send)
    async with factory() as session:
        session.add(Notification(user_id=1, task_id=None, name="global", notification_type="webhook"))
        session.add(Notification(user_id=1, task_id=10, name="target", notification_type="webhook"))
        session.add(Notification(user_id=1, task_id=11, name="other-task", notification_type="webhook"))
        session.add(Notification(user_id=2, task_id=None, name="other-user", notification_type="webhook"))
        await session.commit()
        await QDScheduler()._send_notifications(
            session, 10, 1, "task", "success", task_log="signed in"
        )

    assert len(sent) == 2
    assert all(call["task_log"] == "signed in" for call in sent)
    await engine.dispose()


@pytest.mark.asyncio
async def test_task_notification_switches_and_failure_threshold(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    sent = []

    async def fake_send(**kwargs):
        sent.append(kwargs)

    monkeypatch.setattr("qd_server.services.notification.send_notification", fake_send)
    async with factory() as session:
        session.add(
            Notification(
                user_id=1,
                name="threshold",
                notification_type="webhook",
                config={"failure_threshold": 3},
            )
        )
        session.add(TaskRun(task_id=10, user_id=1, status="failed"))
        session.add(TaskRun(task_id=10, user_id=1, status="failed"))
        await session.commit()

        service = QDScheduler()
        await service._send_notifications(session, 10, 1, "task", "failed", "second")
        assert sent == []

        session.add(TaskRun(task_id=10, user_id=1, status="failed"))
        await session.commit()
        await service._send_notifications(session, 10, 1, "task", "failed", "third")
        assert len(sent) == 1
        assert sent[0]["error_message"] == "third"

        await service._send_notifications(
            session,
            10,
            1,
            "task",
            "failed",
            "disabled",
            execution_config={"notify_on_failure": False},
        )
        assert len(sent) == 1

    await engine.dispose()


@pytest.mark.asyncio
async def test_load_tasks_only_registers_active_runnable_relations(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as session:
        active = User(username="active-scheduler", hashed_password="x")
        inactive = User(username="inactive-scheduler", hashed_password="x", is_active=False)
        session.add(active)
        session.add(inactive)
        await session.flush()
        enabled = Template(user_id=active.id, name="enabled")
        disabled = Template(user_id=active.id, name="disabled", enabled=False)
        inactive_template = Template(user_id=inactive.id, name="inactive-owner")
        session.add(enabled)
        session.add(disabled)
        session.add(inactive_template)
        await session.flush()
        session.add(Task(user_id=active.id, template_id=enabled.id, name="runnable"))
        session.add(Task(user_id=active.id, template_id=disabled.id, name="disabled-template"))
        session.add(Task(user_id=inactive.id, template_id=inactive_template.id, name="inactive-user"))
        await session.commit()

    settings = SimpleNamespace(db=SimpleNamespace(scoped_session=factory))
    monkeypatch.setattr("qd_server.config.get_settings", lambda: settings)
    service = QDScheduler()
    loaded = []
    monkeypatch.setattr(service, "_add_job", lambda task: loaded.append(task.name))

    await service.load_tasks()
    assert loaded == ["runnable"]

    await engine.dispose()


@pytest.mark.asyncio
async def test_scheduled_execution_skips_paused_task_and_inactive_user(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as session:
        active = User(username="active-execute", hashed_password="x")
        inactive = User(username="inactive-execute", hashed_password="x", is_active=False)
        session.add(active)
        session.add(inactive)
        await session.flush()
        active_template = Template(user_id=active.id, name="paused-template")
        inactive_template = Template(user_id=inactive.id, name="inactive-template")
        session.add(active_template)
        session.add(inactive_template)
        await session.flush()
        paused = Task(
            user_id=active.id,
            template_id=active_template.id,
            name="paused",
            status="paused",
        )
        inactive_task = Task(
            user_id=inactive.id,
            template_id=inactive_template.id,
            name="inactive",
        )
        session.add(paused)
        session.add(inactive_task)
        await session.commit()
        await session.refresh(paused)
        await session.refresh(inactive_task)

    settings = SimpleNamespace(db=SimpleNamespace(scoped_session=factory))
    monkeypatch.setattr("qd_server.config.get_settings", lambda: settings)
    service = QDScheduler()

    assert await service._execute_task(paused.id) is None
    assert await service._execute_task(inactive_task.id) is None

    await engine.dispose()


@pytest.mark.asyncio
async def test_execution_publishes_and_persists_extracted_task_log(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as session:
        user = User(username="task-log-user", hashed_password="x")
        session.add(user)
        await session.flush()
        template = Template(
            user_id=user.id,
            name="task-log-template",
            template_data={"name": "task-log-template", "requests": [{"url": "https://example.com/"}]},
        )
        session.add(template)
        await session.flush()
        task = Task(user_id=user.id, template_id=template.id, name="task-log-task")
        session.add(task)
        await session.commit()
        await session.refresh(task)

    class FakeFetcher:
        def __init__(self, cookie_session, proxy=None, api_base_url=None):
            self.session = cookie_session

        async def execute_template(self, _template):
            return [
                {
                    "status": "success",
                    "success": True,
                    "status_code": 200,
                    "url": "https://example.com/",
                    "extracted_variables": {"__log__": "first line\nsecond line", "token": "secret"},
                }
            ]

    settings = SimpleNamespace(db=SimpleNamespace(scoped_session=factory))
    monkeypatch.setattr("qd_server.config.get_settings", lambda: settings)
    monkeypatch.setattr("qd_core.client.fetcher.QDFetcher", FakeFetcher)
    events = []
    monkeypatch.setattr(
        "qd_server.services.log_stream.log_stream.publish",
        lambda user_id, event_type, **data: events.append((user_id, event_type, data)),
    )
    service = QDScheduler()

    async def skip_notifications(*_args, **_kwargs):
        return None

    monkeypatch.setattr(service, "_send_notifications", skip_notifications)
    run = await service._execute_task(task.id, manual=True)

    assert run.response_summary == "first line\nsecond line"
    assert run.extracted_variables == {"__log__": "first line\nsecond line"}
    task_log_events = [data for _, event_type, data in events if event_type == "task_log"]
    assert task_log_events == [
        {
            "task_id": task.id,
            "task_name": "task-log-task",
            "request_index": 0,
            "content": "first line\nsecond line",
        }
    ]

    async with factory() as session:
        stored = (await session.execute(select(TaskRun))).scalar_one()
        assert stored.response_summary == "first line\nsecond line"
        assert stored.extracted_variables == {"__log__": "first line\nsecond line"}

    await engine.dispose()


@pytest.mark.asyncio
async def test_execution_persists_simple_failed_request_log(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as session:
        user = User(username="failed-log-user", hashed_password="x")
        session.add(user)
        await session.flush()
        template = Template(
            user_id=user.id,
            name="failed-log-template",
            template_data={"name": "failed-log-template", "requests": [{"url": "https://example.test/account"}]},
        )
        session.add(template)
        await session.flush()
        task = Task(user_id=user.id, template_id=template.id, name="failed-log-task")
        session.add(task)
        await session.commit()
        await session.refresh(task)

    class FakeFetcher:
        def __init__(self, cookie_session, proxy=None, api_base_url=None):
            self.session = cookie_session

        async def execute_template(self, _template):
            return [
                {
                    "status": "failed",
                    "success": False,
                    "message": "Fail assert: login required",
                    "status_code": 403,
                    "method": "GET",
                    "url": "https://example.test/account",
                    "content": '{"error":"not logged in"}',
                    "request_index": 0,
                    "extracted_variables": {"__log__": "login check failed"},
                }
            ]

    settings = SimpleNamespace(db=SimpleNamespace(scoped_session=factory))
    monkeypatch.setattr("qd_server.config.get_settings", lambda: settings)
    monkeypatch.setattr("qd_core.client.fetcher.QDFetcher", FakeFetcher)
    service = QDScheduler()

    async def skip_notifications(*_args, **_kwargs):
        return None

    monkeypatch.setattr(service, "_send_notifications", skip_notifications)
    run = await service._execute_task(task.id, manual=True)

    assert run.status == "failed"
    assert run.error_message == (
        "Failed at 1/1 request,Fail assert: login required,"
        "Request URL: https://example.test/account"
    )
    assert run.response_summary is None

    async with factory() as session:
        stored = (await session.execute(select(TaskRun))).scalar_one()
        assert stored.error_message == run.error_message
        assert stored.response_summary is None

    await engine.dispose()
