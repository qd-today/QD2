"""End-to-end QD v1 database migration regression tests."""

import base64
import io
import json
import sqlite3

import pytest
import qd_server.models  # noqa: F401 - register all tables
import umsgpack
from Crypto.Cipher import AES
from qd_server.api.migrate import _v1_aes_key, import_v1_data
from qd_server.models.notepad import Notepad
from qd_server.models.notification import Notification
from qd_server.models.task import Task
from qd_server.models.task_group import TaskGroup
from qd_server.models.template import Template
from qd_server.models.user import User
from qd_server.services.encryption import unprotect_dict, unprotect_list
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.datastructures import UploadFile


def _v1_encrypt(value, key: bytes) -> bytes:
    iv = bytes(range(AES.block_size))
    payload = umsgpack.packb(value)
    padding_size = AES.block_size - len(payload) % AES.block_size
    payload += b"\x00" * padding_size
    encrypted = AES.new(key, AES.MODE_CBC, iv).encrypt(payload)
    return umsgpack.packb([encrypted, iv])


def _build_v1_database(path, include_invalid_template: bool = False) -> bytes:
    global_key = _v1_aes_key("binux")
    user_key = b"u" * 32
    har = {
        "log": {
            "version": "1.2",
            "creator": {"name": "QD v1", "version": "1"},
            "entries": [
                {
                    "comment": "login request",
                    "request": {
                        "method": "POST",
                        "url": "https://example.test/login?token={{ token }}",
                        "headers": [{"name": "content-type", "value": "application/json"}],
                        "queryString": [{"name": "token", "value": "{{ token }}"}],
                        "postData": {"mimeType": "application/json", "text": '{"ok":true}'},
                    },
                    "response": {
                        "status": 200,
                        "headers": [{"name": "set-cookie", "value": "sid=test"}],
                    },
                    "rule": {
                        "success_asserts": [{"from": "status", "re": "200"}],
                        "failed_asserts": [],
                        "extract_variables": [],
                    },
                }
            ],
        }
    }

    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE user (
            id INTEGER PRIMARY KEY, nickname TEXT, email TEXT, userkey BLOB,
            skey TEXT, barkurl TEXT, wxpusher TEXT, noticeflg INTEGER,
            qywx_token TEXT, logtime TEXT
        );
        CREATE TABLE tpl (
            id INTEGER PRIMARY KEY, userid INTEGER, har BLOB,
            variables TEXT, sitename TEXT, note TEXT
        );
        CREATE TABLE task (
            id INTEGER PRIMARY KEY, tplid INTEGER, userid INTEGER,
            newontime TEXT, retry_count INTEGER, note TEXT, disabled INTEGER,
            interval_seconds INTEGER, init_env BLOB, session BLOB,
            retry_interval INTEGER, ontimeflg INTEGER, ontime TEXT,
            _groups TEXT, pushsw TEXT
        );
        CREATE TABLE notepad (
            id INTEGER PRIMARY KEY, userid INTEGER, notepadid INTEGER, content TEXT
        );
        CREATE TABLE pubtpl (
            id INTEGER PRIMARY KEY, name TEXT, filename TEXT,
            comments TEXT, content TEXT
        );
        """
    )
    connection.execute(
        "INSERT INTO user VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            1,
            "legacy",
            "legacy@example.test",
            _v1_encrypt(user_key, global_key),
            "SCT-test",
            "https://bark.example.test/device-key",
            "AT_test;UID_test",
            513,
            "wwcorp;1000001;corp-secret;",
            json.dumps({"ErrTolerateCnt": 3}),
        ),
    )
    connection.execute(
        "INSERT INTO tpl VALUES (?, ?, ?, ?, ?, ?)",
        (1, 1, _v1_encrypt(har, user_key), json.dumps(["token"]), "Legacy template", "note"),
    )
    public_content = base64.b64encode(json.dumps(har).encode()).decode()
    connection.execute(
        "INSERT INTO pubtpl VALUES (?, ?, ?, ?, ?)",
        (3, "Legacy public template", "public.har", "public note", public_content),
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
        "INSERT INTO task VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            1,
            1,
            1,
            json.dumps({"sw": True, "time": "00:05:10", "randsw": True, "tz1": -600, "tz2": 30}),
            2,
            "Legacy task",
            0,
            None,
            _v1_encrypt(
                {
                    "token": "task-token",
                    "_proxy": "http://proxy.example.test:8080",
                },
                user_key,
            ),
            _v1_encrypt(
                [{"name": "sid", "value": "legacy-cookie", "domain": "example.test"}],
                user_key,
            ),
            45,
            0,
            "00:10:00",
            "Accounts",
            json.dumps({"pushen": True, "logen": False}),
        ),
    )
    connection.execute(
        "INSERT INTO task VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            2,
            3,
            1,
            "{}",
            0,
            "Public task",
            1,
            3600,
            None,
            None,
            None,
            0,
            "00:10:00",
            "None",
            json.dumps({"pushen": False, "logen": False}),
        ),
    )
    connection.execute("INSERT INTO notepad VALUES (?, ?, ?, ?)", (1, 1, 7, "legacy note"))
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
            "templates_imported": 2,
            "tasks_imported": 2,
            "task_groups_imported": 1,
            "users_imported": 1,
            "notifications_imported": 4,
            "notepads_imported": 1,
            "errors": [],
        }
        imported_user = (
            await session.execute(select(User).where(User.username == "legacy"))
        ).scalar_one()
        assert imported_user.is_active is False

        templates = (await session.execute(select(Template))).scalars().all()
        assert len(templates) == 2
        template = next(row for row in templates if row.name == "Legacy template")
        assert template.user_id == imported_user.id
        assert template.variables == {"token": ""}
        assert len(template.template_data["requests"]) == 1
        request = template.template_data["requests"][0]
        assert request["method"] == "POST"
        assert request["postData"]["text"] == '{"ok":true}'
        assert request["_comment"] == "login request"
        assert request["_hasResponseSetCookie"] is True
        assert request["rule"]["success_asserts"] == [{"from": "status", "re": "200"}]

        notifications = (await session.execute(select(Notification))).scalars().all()
        assert {row.notification_type for row in notifications} == {
            "serverchan",
            "bark",
            "wxpusher",
            "wecom_app",
        }
        assert all(not row.on_success and row.on_failure for row in notifications)
        assert sum(row.enabled for row in notifications) == 1
        wecom = next(row for row in notifications if row.notification_type == "wecom_app")
        assert unprotect_dict(wecom.config, "notification.config") == {
            "corp_id": "wwcorp",
            "agent_id": 1000001,
            "corp_secret": "corp-secret",
            "touser": "@all",
            "failure_threshold": 4,
        }
        assert wecom.enabled is True

        notepad = (await session.execute(select(Notepad))).scalars().one()
        assert notepad.user_id == imported_user.id
        assert notepad.title == "QD v1 记事本 #7"
        assert notepad.content == "legacy note"

        tasks = (await session.execute(select(Task))).scalars().all()
        assert len(tasks) == 2
        task = next(row for row in tasks if row.name == "Legacy template")
        assert task.user_id == imported_user.id
        assert task.template_id == template.id
        assert task.description == "Legacy task"
        assert unprotect_dict(task.variables, "task.variables") == {"token": "task-token"}
        assert unprotect_list(task.cookie_session, "task.cookie_session") == [
            {"name": "sid", "value": "legacy-cookie", "domain": "example.test"}
        ]
        assert task.schedule_config == {
            "schedule_type": "daily",
            "run_time": "23:55:10",
        }
        assert task.execution_config == {
            "retry_count": 2,
            "retry_interval_seconds": 45,
            "proxy": "http://proxy.example.test:8080",
            "random_delay_min": 0,
            "random_delay_max": 630,
            "notify_on_success": True,
            "notify_on_failure": True,
        }
        group = (await session.execute(select(TaskGroup))).scalars().one()
        assert group.name == "Accounts"
        assert task.group_id == group.id

        public_task = next(row for row in tasks if row.name == "Legacy public template")
        assert public_task.description == "Public task"
        assert public_task.status == "disabled"
        assert public_task.schedule_config == {
            "schedule_type": "interval",
            "interval_seconds": 3600,
        }
        assert public_task.execution_config["notify_on_success"] is False
        assert public_task.execution_config["notify_on_failure"] is False

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

        assert result.templates_imported == 2
        assert result.tasks_imported == 2
        assert len(result.errors) == 1
        assert "导入模板 #2 失败" in result.errors[0]
        assert len((await session.execute(select(Template))).scalars().all()) == 2
        assert len((await session.execute(select(Task))).scalars().all()) == 2

    await engine.dispose()
