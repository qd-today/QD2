"""User-scoped backup, restore, and database snapshot tests."""

import json
import sqlite3
from unittest.mock import Mock

import pytest
import qd_server.models  # noqa: F401 - register all tables
from qd_server.api.data_management import (
    _build_user_backup,
    _create_sqlite_snapshot,
    _database_preview,
    _import_user_backup,
    _parse_backup,
    _pending_restore_path,
    apply_pending_database_restore,
)
from qd_server.config import DBSettings, DBType, QDServerSettings, Sqlite3Settings
from qd_server.models.notepad import Notepad
from qd_server.models.notification import Notification
from qd_server.models.task import Task, TaskRun
from qd_server.models.task_group import TaskGroup
from qd_server.models.template import Template
from qd_server.models.template_source import TemplateSource
from qd_server.models.user import User
from qd_server.services.encryption import unprotect_list
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db_session:
        yield db_session
    await engine.dispose()


async def _seed_user_data(session: AsyncSession, user: User, prefix: str) -> Task:
    template = Template(
        user_id=user.id,
        name=f"{prefix}-template",
        template_data={"requests": [{"url": f"https://{prefix}.example.test"}]},
        variables={"token": prefix},
    )
    group = TaskGroup(user_id=user.id, name=f"{prefix}-group")
    session.add(template)
    session.add(group)
    await session.flush()
    task = Task(
        user_id=user.id,
        template_id=template.id,
        group_id=group.id,
        name=f"{prefix}-task",
        schedule_config={"schedule_type": "interval", "interval_seconds": 3600},
        cookie_session=[{"name": "sid", "value": prefix}],
    )
    session.add(task)
    await session.flush()
    session.add(TaskRun(task_id=task.id, user_id=user.id, status="success"))
    session.add(
        Notification(
            user_id=user.id,
            task_id=task.id,
            name=f"{prefix}-notification",
            notification_type="webhook",
            config={"token": prefix},
        )
    )
    session.add(Notepad(user_id=user.id, title=f"{prefix}-note", content=prefix))
    session.add(TemplateSource(user_id=user.id, name=f"{prefix}-source", manifest={"version": prefix}))
    await session.commit()
    return task


@pytest.mark.asyncio
async def test_user_backup_and_replace_import_are_owner_scoped(session, monkeypatch):
    source = User(username="source", hashed_password="source-secret")
    target = User(username="target", hashed_password="target-secret")
    other = User(username="other", hashed_password="other-secret")
    session.add_all([source, target, other])
    await session.commit()
    await session.refresh(source)
    await session.refresh(target)
    await session.refresh(other)

    await _seed_user_data(session, source, "source")
    old_target_task = await _seed_user_data(session, target, "target-old")
    await _seed_user_data(session, other, "other")

    payload = await _build_user_backup(session, source)
    encoded = json.dumps(payload)
    assert "source-template" in encoded
    assert "other-template" not in encoded
    assert "source-secret" not in encoded
    assert "hashed_password" not in encoded

    payload["data"]["templates"][0]["user_id"] = other.id
    from qd_server.services.scheduler import scheduler

    add_task = Mock()
    remove_task = Mock()
    monkeypatch.setattr(scheduler, "add_task", add_task)
    monkeypatch.setattr(scheduler, "remove_task", remove_task)

    result = await _import_user_backup(session, target, payload, "replace")
    assert result.counts["templates"] == 1
    remove_task.assert_called_once_with(old_target_task.id)
    assert add_task.call_count == 1

    target_templates = (
        await session.execute(select(Template).where(Template.user_id == target.id))
    ).scalars().all()
    assert [row.name for row in target_templates] == ["source-template"]
    assert target_templates[0].user_id == target.id

    target_tasks = (await session.execute(select(Task).where(Task.user_id == target.id))).scalars().all()
    assert [row.name for row in target_tasks] == ["source-task"]
    assert target_tasks[0].template_id == target_templates[0].id
    assert target_tasks[0].cookie_session != [{"name": "sid", "value": "source"}]
    assert unprotect_list(target_tasks[0].cookie_session, "task.cookie_session") == [
        {"name": "sid", "value": "source"}
    ]

    assert len((await session.execute(select(TaskRun).where(TaskRun.user_id == target.id))).scalars().all()) == 1
    assert len(
        (await session.execute(select(Notification).where(Notification.user_id == target.id))).scalars().all()
    ) == 1
    assert len((await session.execute(select(Notepad).where(Notepad.user_id == target.id))).scalars().all()) == 1
    assert len(
        (await session.execute(select(TemplateSource).where(TemplateSource.user_id == target.id))).scalars().all()
    ) == 1

    other_templates = (
        await session.execute(select(Template).where(Template.user_id == other.id))
    ).scalars().all()
    assert [row.name for row in other_templates] == ["other-template"]


def test_backup_parser_and_sqlite_snapshot(tmp_path):
    payload = {
        "format": "qd2-user-backup",
        "version": 1,
        "created_at": "2026-08-27T00:00:00",
        "source": {"username": "owner"},
        "data": {
            "templates": [],
            "task_groups": [],
            "tasks": [],
            "task_runs": [],
            "notifications": [],
            "notepads": [],
            "template_sources": [],
        },
    }
    assert _parse_backup(json.dumps(payload).encode("utf-8"))["source"]["username"] == "owner"

    source_path = tmp_path / "source.db"
    snapshot_path = tmp_path / "snapshot.db"
    source = sqlite3.connect(source_path)
    source.execute("CREATE TABLE sample (value TEXT NOT NULL)")
    source.execute("INSERT INTO sample VALUES ('preserved')")
    source.commit()
    source.close()

    _create_sqlite_snapshot(source_path, snapshot_path)
    snapshot = sqlite3.connect(snapshot_path)
    try:
        assert snapshot.execute("SELECT value FROM sample").fetchone()[0] == "preserved"
        assert snapshot.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        snapshot.close()


def _build_minimal_qd2_database(path, marker: str) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            username TEXT NOT NULL,
            hashed_password TEXT NOT NULL,
            role TEXT NOT NULL
        );
        CREATE TABLE templates (id INTEGER PRIMARY KEY);
        CREATE TABLE tasks (id INTEGER PRIMARY KEY);
        CREATE TABLE task_runs (id INTEGER PRIMARY KEY);
        CREATE TABLE marker (value TEXT NOT NULL);
        """
    )
    connection.execute("INSERT INTO users VALUES (1, 'admin', 'hash', 'admin')")
    connection.execute("INSERT INTO marker VALUES (?)", (marker,))
    connection.commit()
    connection.close()


def test_pending_database_restore_replaces_database_and_keeps_backup(tmp_path):
    database_path = tmp_path / "database.db"
    pending_path = _pending_restore_path(database_path)
    _build_minimal_qd2_database(database_path, "current")
    _build_minimal_qd2_database(pending_path, "restored")

    preview = _database_preview(pending_path)
    assert preview.model_dump() == {
        "users": 1,
        "templates": 0,
        "tasks": 0,
        "task_runs": 0,
        "integrity": "ok",
    }

    settings = QDServerSettings(
        db=DBSettings(
            db_type=DBType.sqlite3,
            engine_settings=Sqlite3Settings(db_path=database_path),
        )
    )
    backup_path = apply_pending_database_restore(settings)
    assert backup_path is not None
    assert pending_path.exists() is False

    restored = sqlite3.connect(database_path)
    backup = sqlite3.connect(backup_path)
    try:
        assert restored.execute("SELECT value FROM marker").fetchone()[0] == "restored"
        assert backup.execute("SELECT value FROM marker").fetchone()[0] == "current"
    finally:
        restored.close()
        backup.close()
