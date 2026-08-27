"""Cross-user relation and task lifecycle regression tests."""

from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

import qd_server.models  # noqa: F401 - register all tables
from qd_server.api.notifications import NotificationCreate, create_notification
from qd_server.api.admin import AdminUserUpdate, update_user
from qd_server.api.tasks import (
    TaskBulkRequest,
    TaskCreate,
    TaskUpdate,
    batch_tasks,
    create_task,
    delete_task,
    run_task,
    update_task,
)
from qd_server.api.templates import TemplateUpdate, delete_template, update_template
from qd_server.models.notification import Notification
from qd_server.models.task import Task, TaskRun
from qd_server.models.task_group import TaskGroup
from qd_server.models.template import Template
from qd_server.models.user import User


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db_session:
        yield db_session
    await engine.dispose()


async def _seed(session: AsyncSession):
    owner = User(username="owner-rel", hashed_password="x")
    other = User(username="other-rel", hashed_password="x")
    session.add(owner)
    session.add(other)
    await session.flush()
    owner_template = Template(user_id=owner.id, name="owned")
    other_template = Template(user_id=other.id, name="foreign")
    owner_group = TaskGroup(user_id=owner.id, name="owned")
    other_group = TaskGroup(user_id=other.id, name="foreign")
    session.add(owner_template)
    session.add(other_template)
    session.add(owner_group)
    session.add(other_group)
    await session.commit()
    return owner, other, owner_template, other_template, owner_group, other_group


@pytest.mark.asyncio
async def test_task_relations_schedule_and_cleanup_are_isolated(session, monkeypatch):
    owner, _, owned_template, foreign_template, owned_group, foreign_group = await _seed(session)
    from qd_server.services.scheduler import scheduler

    add_task = Mock()
    remove_task = Mock()
    monkeypatch.setattr(scheduler, "add_task", add_task)
    monkeypatch.setattr(scheduler, "remove_task", remove_task)

    with pytest.raises(HTTPException) as foreign_template_error:
        await create_task(
            TaskCreate(template_id=foreign_template.id, name="invalid"),
            owner,
            session,
        )
    assert foreign_template_error.value.status_code == 404

    created = await create_task(
        TaskCreate(
            template_id=owned_template.id,
            group_id=owned_group.id,
            name="valid",
            schedule_config={"schedule_type": "daily", "run_time": "08:30:15"},
        ),
        owner,
        session,
    )
    assert created.group_id == owned_group.id
    assert add_task.call_count == 1

    with pytest.raises(HTTPException) as foreign_group_error:
        await update_task(
            created.id,
            TaskUpdate(group_id=foreign_group.id),
            owner,
            session,
        )
    assert foreign_group_error.value.status_code == 404

    await update_task(created.id, TaskUpdate(status="paused"), owner, session)
    remove_task.assert_called_once_with(created.id)

    session.add(TaskRun(task_id=created.id, user_id=owner.id, status="success"))
    session.add(
        Notification(
            user_id=owner.id,
            task_id=created.id,
            name="linked",
            notification_type="webhook",
        )
    )
    await session.commit()

    with pytest.raises(HTTPException) as template_in_use:
        await delete_template(owned_template.id, owner, session)
    assert template_in_use.value.status_code == 409

    await delete_task(created.id, owner, session)
    assert (await session.execute(select(TaskRun))).scalars().all() == []
    assert (await session.execute(select(Notification))).scalars().all() == []
    remove_task.assert_called_with(created.id)


@pytest.mark.asyncio
async def test_notification_cannot_bind_foreign_task(session):
    owner, other, owned_template, _, _, _ = await _seed(session)
    task = Task(user_id=other.id, template_id=owned_template.id, name="foreign-task")
    session.add(task)
    await session.commit()
    await session.refresh(task)

    with pytest.raises(HTTPException) as error:
        await create_notification(
            NotificationCreate(
                name="invalid",
                notification_type="webhook",
                task_id=task.id,
            ),
            owner,
            session,
        )
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_invalid_schedule_is_rejected(session):
    owner, _, owned_template, _, _, _ = await _seed(session)
    with pytest.raises(HTTPException) as error:
        await create_task(
            TaskCreate(
                template_id=owned_template.id,
                name="invalid-time",
                schedule_config={"schedule_type": "daily", "run_time": "25:99"},
            ),
            owner,
            session,
        )
    assert error.value.status_code == 422


@pytest.mark.asyncio
async def test_batch_task_operations_are_owner_scoped(session, monkeypatch):
    owner, other, owned_template, other_template, owned_group, _ = await _seed(session)
    first = Task(user_id=owner.id, template_id=owned_template.id, name="first")
    second = Task(user_id=owner.id, template_id=owned_template.id, name="second")
    foreign = Task(user_id=other.id, template_id=other_template.id, name="foreign")
    session.add_all([first, second, foreign])
    await session.commit()

    from qd_server.services.scheduler import scheduler

    add_task = Mock()
    remove_task = Mock()
    monkeypatch.setattr(scheduler, "add_task", add_task)
    monkeypatch.setattr(scheduler, "remove_task", remove_task)

    disabled = await batch_tasks(
        TaskBulkRequest(task_ids=[first.id, second.id], action="disable"),
        owner,
        session,
    )
    assert disabled.affected == 2
    assert first.status == second.status == "disabled"
    assert remove_task.call_count == 2

    await batch_tasks(
        TaskBulkRequest(
            task_ids=[first.id, second.id],
            action="group",
            group_id=owned_group.id,
        ),
        owner,
        session,
    )
    assert first.group_id == second.group_id == owned_group.id

    await batch_tasks(
        TaskBulkRequest(
            task_ids=[first.id, second.id],
            action="schedule",
            schedule_config={"schedule_type": "daily", "run_time": "06:30:15"},
        ),
        owner,
        session,
    )
    assert first.schedule_config == second.schedule_config == {
        "schedule_type": "daily",
        "run_time": "06:30:15",
    }
    assert add_task.call_count == 0

    await batch_tasks(
        TaskBulkRequest(task_ids=[first.id, second.id], action="enable"),
        owner,
        session,
    )
    assert first.status == second.status == "pending"
    assert add_task.call_count == 2

    with pytest.raises(HTTPException) as foreign_error:
        await batch_tasks(
            TaskBulkRequest(task_ids=[first.id, foreign.id], action="disable"),
            owner,
            session,
        )
    assert foreign_error.value.status_code == 404

    deleted = await batch_tasks(
        TaskBulkRequest(task_ids=[second.id], action="delete"),
        owner,
        session,
    )
    assert deleted.affected == 1
    assert (
        await session.execute(select(Task).where(Task.id == second.id))
    ).scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_manual_run_does_not_return_stale_history(session, monkeypatch):
    owner, _, owned_template, _, _, _ = await _seed(session)
    task = Task(user_id=owner.id, template_id=owned_template.id, name="manual")
    session.add(task)
    await session.flush()
    session.add(TaskRun(task_id=task.id, user_id=owner.id, status="success"))
    await session.commit()
    await session.refresh(task)

    from qd_server.services.scheduler import scheduler

    async def no_new_run(_task_id):
        return None

    monkeypatch.setattr(scheduler, "run_task_now", no_new_run)
    with pytest.raises(HTTPException) as error:
        await run_task(task.id, owner, session)
    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_user_and_template_state_sync_scheduler(session, monkeypatch):
    owner, other, _, other_template, _, _ = await _seed(session)
    owner.role = "admin"
    task = Task(user_id=other.id, template_id=other_template.id, name="lifecycle")
    session.add(owner)
    session.add(task)
    await session.commit()
    await session.refresh(task)

    from qd_server.services.scheduler import scheduler

    add_task = Mock()
    remove_task = Mock()
    monkeypatch.setattr(scheduler, "add_task", add_task)
    monkeypatch.setattr(scheduler, "remove_task", remove_task)

    await update_user(other.id, AdminUserUpdate(is_active=False), owner, session)
    remove_task.assert_called_with(task.id)

    await update_user(other.id, AdminUserUpdate(is_active=True), owner, session)
    add_task.assert_called_with(task)

    await update_template(
        other_template.id,
        TemplateUpdate(enabled=False),
        other,
        session,
    )
    remove_task.assert_called_with(task.id)

    await update_template(
        other_template.id,
        TemplateUpdate(enabled=True),
        other,
        session,
    )
    assert add_task.call_count == 2
