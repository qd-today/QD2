"""Task and template list statistics regression tests."""

from datetime import datetime

import pytest
import qd_server.models  # noqa: F401 - register all tables
from qd_server.api.tasks import list_tasks
from qd_server.api.templates import list_templates
from qd_server.models.task import Task, TaskRun
from qd_server.models.template import Template
from qd_server.models.user import User
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
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


@pytest.mark.asyncio
async def test_task_and_template_statistics_are_scoped_to_owner(
    session: AsyncSession, monkeypatch
) -> None:
    owner = User(username="stats-owner", hashed_password="x")
    other = User(username="stats-other", hashed_password="x")
    session.add(owner)
    session.add(other)
    await session.flush()

    owner_template = Template(user_id=owner.id, name="owner template")
    other_template = Template(user_id=other.id, name="other template")
    session.add(owner_template)
    session.add(other_template)
    await session.flush()

    owner_task = Task(user_id=owner.id, template_id=owner_template.id, name="owner task")
    other_task = Task(user_id=other.id, template_id=other_template.id, name="other task")
    session.add(owner_task)
    session.add(other_task)
    await session.flush()

    first_success = datetime(2026, 1, 2, 3, 4, 5)
    latest_success = datetime(2026, 2, 3, 4, 5, 6)
    next_run = datetime(2026, 3, 4, 5, 6, 7)
    session.add(TaskRun(task_id=owner_task.id, user_id=owner.id, status="success", finished_at=first_success))
    session.add(TaskRun(task_id=owner_task.id, user_id=owner.id, status="failed"))
    session.add(TaskRun(task_id=owner_task.id, user_id=owner.id, status="success", finished_at=latest_success))
    # A malformed cross-user row must not affect the owner's counts or dates.
    session.add(
        TaskRun(
            task_id=owner_task.id,
            user_id=other.id,
            status="success",
            finished_at=datetime(2030, 1, 1),
        )
    )
    await session.commit()

    from qd_server.services.scheduler import scheduler

    monkeypatch.setattr(
        scheduler,
        "get_next_run_time",
        lambda task_id: next_run if task_id == owner_task.id else None,
    )

    task_page = await list_tasks(1, 20, None, owner, session)
    assert task_page.total == 1
    task_row = task_page.items[0]
    assert task_row.success_count == 2
    assert task_row.failed_count == 1
    assert task_row.last_success_at == latest_success
    assert task_row.next_run_at == next_run

    template_page = await list_templates(1, 20, None, owner, session)
    assert template_page.total == 1
    assert template_page.items[0].last_success_at == latest_success
