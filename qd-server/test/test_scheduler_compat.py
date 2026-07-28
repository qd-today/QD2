"""Scheduler compatibility and notification isolation tests."""

from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

import qd_server.models  # noqa: F401 - register all tables
from qd_server.models.notification import Notification
from qd_server.models.task import Task
from qd_server.models.template import Template
from qd_server.models.user import User
from qd_server.services.scheduler import QDScheduler


class SchedulerCapture:
    def __init__(self):
        self.job = None

    def get_job(self, _job_id):
        return None

    def add_job(self, func, **kwargs):
        self.job = (func, kwargs)


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
        await QDScheduler()._send_notifications(session, 10, 1, "task", "success")

    assert len(sent) == 2
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
