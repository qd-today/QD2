"""Small, idempotent schema upgrades for databases created before migrations existed."""

from sqlalchemy import inspect
from sqlalchemy.engine import Connection


def upgrade_database_schema(connection: Connection) -> list[str]:
    """Add columns introduced after the initial QD2 database schema.

    ``SQLModel.metadata.create_all`` creates missing tables but intentionally
    does not alter existing ones. Keep these additive upgrades idempotent so an
    older database can start directly on the current release.
    """
    inspector = inspect(connection)
    if "tasks" not in inspector.get_table_names():
        return []

    applied: list[str] = []
    existing_columns = {column["name"] for column in inspector.get_columns("tasks")}
    group_id_type = "INTEGER REFERENCES task_groups(id)" if connection.dialect.name == "sqlite" else "INTEGER"
    missing_columns = {
        "group_id": group_id_type,
        "cookie_session": "JSON",
        "execution_config": "JSON",
    }

    for column_name, column_type in missing_columns.items():
        if column_name in existing_columns:
            continue
        connection.exec_driver_sql(f"ALTER TABLE tasks ADD COLUMN {column_name} {column_type}")
        applied.append(f"tasks.{column_name}")

    # Existing rows predate these JSON fields. Store valid empty values so ORM
    # reads behave exactly like rows created with the current model defaults.
    connection.exec_driver_sql("UPDATE tasks SET cookie_session = '[]' WHERE cookie_session IS NULL")
    connection.exec_driver_sql("UPDATE tasks SET execution_config = '{}' WHERE execution_config IS NULL")

    existing_indexes = {index["name"] for index in inspect(connection).get_indexes("tasks")}
    if "ix_tasks_group_id" not in existing_indexes:
        connection.exec_driver_sql("CREATE INDEX ix_tasks_group_id ON tasks (group_id)")
        applied.append("ix_tasks_group_id")

    return applied
