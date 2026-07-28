"""End-to-end QD v1 database migration regression tests."""

import io
import json
import sqlite3

import pytest
import umsgpack
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.datastructures import UploadFile

import qd_server.models  # noqa: F401 - register all tables
from qd_server.api.migrate import _v1_aes_key, import_v1_data
from qd_server.models.task import Task
from qd_server.models.template import Template
from qd_server.models.user import User


def _v1_encrypt(value, key: bytes) -> bytes:
    iv = bytes(range(AES.block_size))
    payload = umsgpack.packb(value)
    encrypted = AES.new(key, AES.MODE_CBC, iv).encrypt(pad(payload, AES.block_size))
    return umsgpack.packb([encrypted, iv])


def _build_v1_database(path, include_invalid_template: bool = False) -> bytes:
    global_key = _v1_aes_key("binux")
    user_key = b"u" * 32
    har = [{"request": {"method": "GET", "url": "https://example.test/{{ token }}"}}]

    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE user (
            id INTEGER PRIMARY KEY, nickname TEXT, email TEXT, userkey BLOB
        );
        CREATE TABLE tpl (
            id INTEGER PRIMARY KEY, userid INTEGER, har BLOB,
            variables TEXT, sitename TEXT, note TEXT
        );
        CREATE TABLE task (
            id INTEGER PRIMARY KEY, tplid INTEGER, userid INTEGER,
            newontime TEXT, retry_count INTEGER, note TEXT, disabled INTEGER,
            interval_seconds INTEGER
        );
        """
    )
    connection.execute(
        "INSERT INTO user VALUES (?, ?, ?, ?)",
        (1, "legacy", "legacy@example.test", _v1_encrypt(user_key, global_key)),
    )
    connection.execute(
        "INSERT INTO tpl VALUES (?, ?, ?, ?, ?, ?)",
        (1, 1, _v1_encrypt(har, user_key), json.dumps(["token"]), "Legacy template", "note"),
    )
    if include_invalid_template:
        connection.execute(
            "INSERT INTO tpl VALUES (?, ?, ?, ?, ?, ?)",
            (
                2,
                1,
                _v1_encrypt({"not_json": b"\xff"}, user_key),
                "[]",
                "Invalid template",
                "must be isolated",
            ),
        )
    connection.execute(
        "INSERT INTO task VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            1,
            1,
            1,
            json.dumps({"sw": True, "time": "00:05:10", "randsw": True, "tz1": -600, "tz2": 30}),
            2,
            "Legacy task",
            0,
            None,
        ),
    )
    connection.commit()
    connection.close()
    return path.read_bytes()


@pytest.mark.asyncio
async def test_real_encrypted_v1_database_import(tmp_path):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as session:
        admin = User(username="admin", hashed_password="x", role="admin")
        session.add(admin)
        await session.commit()
        await session.refresh(admin)

        content = _build_v1_database(tmp_path / "v1.db")
        upload = UploadFile(filename="database.DB", file=io.BytesIO(content))
        result = await import_v1_data(
            file=upload,
            aes_key="binux",
            current_user=admin,
            session=session,
        )

        assert result.model_dump() == {
            "templates_imported": 1,
            "tasks_imported": 1,
            "users_imported": 1,
            "errors": [],
        }
        imported_user = (
            await session.execute(select(User).where(User.username == "legacy"))
        ).scalar_one()
        assert imported_user.is_active is False

        template = (await session.execute(select(Template))).scalars().one()
        assert template.user_id == imported_user.id
        assert template.variables == {"token": ""}

        task = (await session.execute(select(Task))).scalars().one()
        assert task.user_id == imported_user.id
        assert task.template_id == template.id
        assert task.schedule_config == {
            "schedule_type": "daily",
            "run_time": "23:55:10",
        }
        assert task.execution_config == {
            "retry_count": 2,
            "random_delay_min": 0,
            "random_delay_max": 630,
        }

    await engine.dispose()


@pytest.mark.asyncio
async def test_invalid_v1_row_does_not_abort_valid_rows(tmp_path):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as session:
        admin = User(username="admin-partial", hashed_password="x", role="admin")
        session.add(admin)
        await session.commit()
        await session.refresh(admin)

        content = _build_v1_database(
            tmp_path / "partially-invalid.db",
            include_invalid_template=True,
        )
        result = await import_v1_data(
            file=UploadFile(filename="database.db", file=io.BytesIO(content)),
            aes_key="binux",
            current_user=admin,
            session=session,
        )

        assert result.templates_imported == 1
        assert result.tasks_imported == 1
        assert len(result.errors) == 1
        assert "导入模板 #2 失败" in result.errors[0]
        assert len((await session.execute(select(Template))).scalars().all()) == 1
        assert len((await session.execute(select(Task))).scalars().all()) == 1

    await engine.dispose()
