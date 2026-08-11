"""Regression tests for upgrading databases created by older QD2 builds."""

import pytest
import qd_server.models  # noqa: F401 - register all tables
from qd_server.schema_migrations import upgrade_database_schema
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel

LEGACY_TASKS_DDL = """
CREATE TABLE tasks (
    id INTEGER PRIMARY KEY,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    user_id INTEGER NOT NULL,
    template_id INTEGER NOT NULL,
    name VARCHAR(200) NOT NULL,
    description VARCHAR(1000),
    schedule_config JSON,
    status VARCHAR(20) NOT NULL,
    variables JSON,
    next_run_at DATETIME,
    run_count INTEGER NOT NULL,
    last_run_at DATETIME,
    last_status VARCHAR(20)
)
"""


@pytest.mark.asyncio
async def test_upgrade_adds_missing_task_columns_without_losing_rows():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    async with engine.begin() as connection:
        await connection.exec_driver_sql(LEGACY_TASKS_DDL)
        await connection.exec_driver_sql(
            """
            INSERT INTO tasks (
                id, created_at, updated_at, user_id, template_id, name,
                schedule_config, status, variables, run_count
            ) VALUES (
                1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1, 1, 'legacy task',
                '{}', 'pending', '{}', 0
            )
            """
        )
        await connection.run_sync(SQLModel.metadata.create_all)
        first_upgrade = await connection.run_sync(upgrade_database_schema)
        second_upgrade = await connection.run_sync(upgrade_database_schema)

        columns = await connection.run_sync(
            lambda sync_connection: {
                column["name"] for column in inspect(sync_connection).get_columns("tasks")
            }
        )
        indexes = await connection.run_sync(
            lambda sync_connection: {
                index["name"] for index in inspect(sync_connection).get_indexes("tasks")
            }
        )
        row = (
            await connection.exec_driver_sql(
                "SELECT name, group_id, cookie_session, execution_config FROM tasks WHERE id = 1"
            )
        ).one()

    assert set(first_upgrade) == {
        "tasks.group_id",
        "tasks.cookie_session",
        "tasks.execution_config",
        "ix_tasks_group_id",
    }
    assert second_upgrade == []
    assert {"group_id", "cookie_session", "execution_config"} <= columns
    assert "ix_tasks_group_id" in indexes
    assert row == ("legacy task", None, "[]", "{}")

    await engine.dispose()
