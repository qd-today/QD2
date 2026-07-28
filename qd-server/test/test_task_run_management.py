"""Task run statistics, cleanup, and ownership isolation tests."""

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

import qd_server.models  # noqa: F401 - register all tables
from qd_server.api.tasks import delete_task_runs, get_task_run_stats
from qd_server.models.task import Task, TaskRun
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
    owner = User(username="owner", hashed_password="x")
    other = User(username="other", hashed_password="x")
    session.add(owner)
    session.add(other)
    await session.flush()
    task = Task(user_id=owner.id, template_id=1, name="task")
    session.add(task)
    await session.flush()
    session.add(TaskRun(task_id=task.id, user_id=owner.id, status="success"))
    session.add(TaskRun(task_id=task.id, user_id=owner.id, status="failed"))
    # A malformed cross-user row must never be disclosed or deleted.
    session.add(TaskRun(task_id=task.id, user_id=other.id, status="success"))
    await session.commit()
    return owner, other, task


@pytest.mark.asyncio
async def test_stats_and_cleanup_are_scoped_to_owner(session):
    owner, _, task = await _seed(session)
    stats = await get_task_run_stats(task.id, owner, session)
    assert stats.model_dump() == {"total": 2, "success": 1, "failed": 1, "other": 0}

    result = await delete_task_runs(task.id, "success", owner, session)
    assert result["deleted"] == 1
    remaining = (await session.execute(select(TaskRun))).scalars().all()
    assert sorted((run.user_id, run.status) for run in remaining) == [
        (owner.id, "failed"),
        (owner.id + 1, "success"),
    ]


@pytest.mark.asyncio
async def test_other_user_cannot_cleanup_task_runs(session):
    _, other, task = await _seed(session)
    with pytest.raises(HTTPException) as error:
        await delete_task_runs(task.id, None, other, session)
    assert error.value.status_code == 404
