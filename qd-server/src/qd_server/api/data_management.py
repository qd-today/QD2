"""QD2 user-scoped data backup and restore APIs."""

import asyncio
import contextlib
import json
import os
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ValidationError
from sqlalchemy import delete as sql_delete
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.background import BackgroundTask

from qd_server.config import DBType, QDServerSettings, Sqlite3Settings, get_settings
from qd_server.middleware.auth import get_current_user, get_session, require_admin
from qd_server.models.notepad import Notepad
from qd_server.models.notification import Notification
from qd_server.models.task import Task, TaskRun
from qd_server.models.task_group import TaskGroup
from qd_server.models.template import Template
from qd_server.models.template_source import TemplateSource
from qd_server.models.user import User
from qd_server.services.encryption import protect_dict, protect_list, unprotect_dict, unprotect_list

router = APIRouter()

BACKUP_FORMAT = "qd2-user-backup"
BACKUP_VERSION = 1
MAX_BACKUP_SIZE = 100 * 1024 * 1024
MAX_DATABASE_BACKUP_SIZE = 1024 * 1024 * 1024
MAX_BACKUP_RECORDS = 500_000
DATA_SECTIONS = (
    "templates",
    "task_groups",
    "tasks",
    "task_runs",
    "notifications",
    "notepads",
    "template_sources",
)


class BackupPreview(BaseModel):
    format: str
    version: int
    source_username: str
    created_at: str
    counts: dict[str, int]
    warnings: list[str]


class ImportResult(BaseModel):
    mode: str
    counts: dict[str, int]
    warnings: list[str]


class DatabasePreview(BaseModel):
    users: int
    templates: int
    tasks: int
    task_runs: int
    integrity: str


class DatabaseRestoreResult(BaseModel):
    staged: bool
    restart_required: bool
    preview: DatabasePreview


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _record_id(record: dict[str, Any], section: str, index: int) -> int:
    value = record.get("backup_id")
    if not isinstance(value, int) or value < 1:
        raise ValueError(f"{section}[{index}].backup_id 必须是正整数")
    return value


def _validated_model(model_type, values: dict[str, Any], section: str, index: int):
    try:
        return model_type.model_validate(values)
    except ValidationError as exc:
        raise ValueError(f"{section}[{index}] 数据无效: {exc.errors()[0]['msg']}") from exc


async def _user_rows(session: AsyncSession, model_type, user_id: int):
    result = await session.execute(select(model_type).where(model_type.user_id == user_id).order_by(model_type.id))
    return result.scalars().all()


async def _build_user_backup(session: AsyncSession, user: User) -> dict[str, Any]:
    templates = await _user_rows(session, Template, user.id)
    groups = await _user_rows(session, TaskGroup, user.id)
    tasks = await _user_rows(session, Task, user.id)
    runs = await _user_rows(session, TaskRun, user.id)
    notifications = await _user_rows(session, Notification, user.id)
    notepads = await _user_rows(session, Notepad, user.id)
    sources = await _user_rows(session, TemplateSource, user.id)

    template_ids = {row.id for row in templates}
    group_ids = {row.id for row in groups}
    exported_tasks = [row for row in tasks if row.template_id in template_ids]
    task_ids = {row.id for row in exported_tasks}

    data = {
        "templates": [
            {
                "backup_id": row.id,
                "name": row.name,
                "description": row.description,
                "author": row.author,
                "version": row.version,
                "template_data": row.template_data,
                "variables": row.variables,
                "enabled": row.enabled,
                "is_public": row.is_public,
                "tags": row.tags,
                "run_count": row.run_count,
                "last_run_at": row.last_run_at,
            }
            for row in templates
        ],
        "task_groups": [
            {
                "backup_id": row.id,
                "name": row.name,
                "description": row.description,
                "sort_order": row.sort_order,
                "color": row.color,
            }
            for row in groups
        ],
        "tasks": [
            {
                "backup_id": row.id,
                "template_backup_id": row.template_id if row.template_id in template_ids else None,
                "group_backup_id": row.group_id if row.group_id in group_ids else None,
                "name": row.name,
                "description": row.description,
                "schedule_config": row.schedule_config,
                "status": row.status,
                "variables": unprotect_dict(row.variables, "task.variables"),
                "cookie_session": unprotect_list(row.cookie_session, "task.cookie_session"),
                "execution_config": row.execution_config,
                "next_run_at": _iso(row.next_run_at),
                "run_count": row.run_count,
                "last_run_at": _iso(row.last_run_at),
                "last_status": row.last_status,
            }
            for row in exported_tasks
        ],
        "task_runs": [
            {
                "task_backup_id": row.task_id,
                "status": row.status,
                "started_at": _iso(row.started_at),
                "finished_at": _iso(row.finished_at),
                "duration_seconds": row.duration_seconds,
                "error_message": row.error_message,
                "response_summary": row.response_summary,
                "extracted_variables": row.extracted_variables,
            }
            for row in runs
            if row.task_id in task_ids
        ],
        "notifications": [
            {
                "task_backup_id": row.task_id if row.task_id in task_ids else None,
                "name": row.name,
                "notification_type": row.notification_type,
                "enabled": row.enabled,
                "config": unprotect_dict(row.config, "notification.config"),
                "on_success": row.on_success,
                "on_failure": row.on_failure,
            }
            for row in notifications
        ],
        "notepads": [
            {
                "title": row.title,
                "content": row.content,
                "category": row.category,
                "tags": row.tags,
                "sort_order": row.sort_order,
            }
            for row in notepads
        ],
        "template_sources": [
            {
                "name": row.name,
                "url": row.url,
                "enabled": row.enabled,
                "last_sync_at": _iso(row.last_sync_at),
                "manifest_version": row.manifest_version,
                "template_count": row.template_count,
                "manifest": row.manifest,
            }
            for row in sources
        ],
    }

    return {
        "format": BACKUP_FORMAT,
        "version": BACKUP_VERSION,
        "created_at": datetime.utcnow().isoformat(),
        "source": {"username": user.username},
        "data": data,
    }


def _parse_backup(content: bytes) -> dict[str, Any]:
    if len(content) > MAX_BACKUP_SIZE:
        raise HTTPException(status_code=413, detail="备份文件不能超过 100 MiB")
    try:
        payload = json.loads(content.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="备份文件不是有效的 UTF-8 JSON") from exc

    if not isinstance(payload, dict) or payload.get("format") != BACKUP_FORMAT:
        raise HTTPException(status_code=400, detail="不是 QD2 用户数据备份文件")
    if payload.get("version") != BACKUP_VERSION:
        raise HTTPException(status_code=400, detail=f"不支持的备份版本: {payload.get('version')}")
    if not isinstance(payload.get("source"), dict) or not isinstance(payload.get("data"), dict):
        raise HTTPException(status_code=400, detail="备份文件结构不完整")

    total_records = 0
    for section in DATA_SECTIONS:
        records = payload["data"].get(section, [])
        if not isinstance(records, list) or any(not isinstance(record, dict) for record in records):
            raise HTTPException(status_code=400, detail=f"备份分区 {section} 必须是对象数组")
        total_records += len(records)
    if total_records > MAX_BACKUP_RECORDS:
        raise HTTPException(status_code=413, detail="备份记录数量过多")
    return payload


async def _read_backup_upload(file: UploadFile) -> dict[str, Any]:
    if not file.filename or not file.filename.lower().endswith(".json"):
        raise HTTPException(status_code=400, detail="请上传 .json 格式的 QD2 备份文件")
    return _parse_backup(await file.read(MAX_BACKUP_SIZE + 1))


def _preview(payload: dict[str, Any]) -> BackupPreview:
    data = payload["data"]
    return BackupPreview(
        format=payload["format"],
        version=payload["version"],
        source_username=str(payload["source"].get("username") or ""),
        created_at=str(payload.get("created_at") or ""),
        counts={section: len(data.get(section, [])) for section in DATA_SECTIONS},
        warnings=["备份可能包含 Cookie、通知令牌和其他敏感配置，请仅导入可信文件。"],
    )


async def _delete_user_data(session: AsyncSession, user_id: int) -> list[int]:
    task_ids = list((await session.execute(select(Task.id).where(Task.user_id == user_id))).scalars().all())
    for model_type in (TaskRun, Notification, Task, TemplateSource, TaskGroup, Notepad, Template):
        await session.execute(sql_delete(model_type).where(model_type.user_id == user_id))
    return task_ids


async def _import_user_backup(
    session: AsyncSession,
    user: User,
    payload: dict[str, Any],
    mode: Literal["merge", "replace"],
) -> ImportResult:
    data = payload["data"]
    old_task_ids: list[int] = []
    imported_tasks: list[Task] = []
    warnings: list[str] = []

    try:
        if mode == "replace":
            old_task_ids = await _delete_user_data(session, user.id)

        template_map: dict[int, int] = {}
        for index, record in enumerate(data["templates"]):
            backup_id = _record_id(record, "templates", index)
            if backup_id in template_map:
                raise ValueError(f"templates[{index}].backup_id 重复")
            values = {key: value for key, value in record.items() if key not in {"backup_id", "id", "user_id"}}
            template = _validated_model(Template, {**values, "user_id": user.id}, "templates", index)
            session.add(template)
            await session.flush()
            if template.id is None:
                raise RuntimeError("数据库未生成模板 ID")
            template_map[backup_id] = template.id

        group_map: dict[int, int] = {}
        for index, record in enumerate(data["task_groups"]):
            backup_id = _record_id(record, "task_groups", index)
            if backup_id in group_map:
                raise ValueError(f"task_groups[{index}].backup_id 重复")
            values = {key: value for key, value in record.items() if key not in {"backup_id", "id", "user_id"}}
            group = _validated_model(TaskGroup, {**values, "user_id": user.id}, "task_groups", index)
            session.add(group)
            await session.flush()
            if group.id is None:
                raise RuntimeError("数据库未生成任务分组 ID")
            group_map[backup_id] = group.id

        task_map: dict[int, int] = {}
        for index, record in enumerate(data["tasks"]):
            backup_id = _record_id(record, "tasks", index)
            if backup_id in task_map:
                raise ValueError(f"tasks[{index}].backup_id 重复")
            template_backup_id = record.get("template_backup_id")
            if template_backup_id not in template_map:
                raise ValueError(f"tasks[{index}] 引用了不存在的模板")
            group_backup_id = record.get("group_backup_id")
            if group_backup_id is not None and group_backup_id not in group_map:
                raise ValueError(f"tasks[{index}] 引用了不存在的任务分组")
            values = {
                key: value
                for key, value in record.items()
                if key
                not in {
                    "backup_id",
                    "id",
                    "user_id",
                    "template_backup_id",
                    "group_backup_id",
                }
            }
            if values.get("status") == "running":
                values["status"] = "pending"
            task = _validated_model(
                Task,
                {
                    **values,
                    "user_id": user.id,
                    "template_id": template_map[template_backup_id],
                    "group_id": group_map.get(group_backup_id),
                },
                "tasks",
                index,
            )
            task.variables = protect_dict(task.variables, "task.variables")
            task.cookie_session = protect_list(task.cookie_session, "task.cookie_session")
            session.add(task)
            await session.flush()
            if task.id is None:
                raise RuntimeError("数据库未生成任务 ID")
            task_map[backup_id] = task.id
            imported_tasks.append(task)

        for index, record in enumerate(data["task_runs"]):
            task_backup_id = record.get("task_backup_id")
            if task_backup_id not in task_map:
                raise ValueError(f"task_runs[{index}] 引用了不存在的任务")
            values = {
                key: value
                for key, value in record.items()
                if key not in {"id", "user_id", "task_id", "task_backup_id"}
            }
            run = _validated_model(
                TaskRun,
                {**values, "user_id": user.id, "task_id": task_map[task_backup_id]},
                "task_runs",
                index,
            )
            session.add(run)

        for index, record in enumerate(data["notifications"]):
            task_backup_id = record.get("task_backup_id")
            if task_backup_id is not None and task_backup_id not in task_map:
                raise ValueError(f"notifications[{index}] 引用了不存在的任务")
            values = {
                key: value
                for key, value in record.items()
                if key not in {"id", "user_id", "task_id", "task_backup_id"}
            }
            notification = _validated_model(
                Notification,
                {
                    **values,
                    "user_id": user.id,
                    "task_id": task_map.get(task_backup_id),
                },
                "notifications",
                index,
            )
            notification.config = protect_dict(notification.config, "notification.config")
            session.add(notification)

        for index, record in enumerate(data["notepads"]):
            values = {key: value for key, value in record.items() if key not in {"id", "user_id"}}
            session.add(_validated_model(Notepad, {**values, "user_id": user.id}, "notepads", index))

        for index, record in enumerate(data["template_sources"]):
            values = {key: value for key, value in record.items() if key not in {"id", "user_id"}}
            session.add(
                _validated_model(TemplateSource, {**values, "user_id": user.id}, "template_sources", index)
            )

        await session.commit()
    except (ValueError, TypeError) as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        await session.rollback()
        raise

    from qd_server.services.scheduler import scheduler

    if mode == "replace":
        for task_id in old_task_ids:
            scheduler.remove_task(task_id)
    for task in imported_tasks:
        if task.status in ("paused", "disabled"):
            continue
        try:
            scheduler.add_task(task)
        except Exception as exc:
            warnings.append(f"任务 #{task.id} 调度失败: {exc}")

    return ImportResult(
        mode=mode,
        counts={section: len(data[section]) for section in DATA_SECTIONS},
        warnings=warnings,
    )


@router.get("/export")
async def export_my_data(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    payload = await _build_user_backup(session, current_user)
    content = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return Response(
        content=content,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="qd2-user-backup-{timestamp}.json"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/import/preview", response_model=BackupPreview)
async def preview_my_data_import(
    file: Annotated[UploadFile, File()],
    current_user: Annotated[User, Depends(get_current_user)],
):
    del current_user
    return _preview(await _read_backup_upload(file))


@router.post("/import", response_model=ImportResult)
async def import_my_data(
    file: Annotated[UploadFile, File()],
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    mode: Annotated[Literal["merge", "replace"], Form()] = "merge",
):
    payload = await _read_backup_upload(file)
    return await _import_user_backup(session, current_user, payload, mode)


def _create_sqlite_snapshot(source_path: Path, target_path: Path) -> None:
    source = sqlite3.connect(f"file:{source_path.as_posix()}?mode=ro", uri=True)
    target = sqlite3.connect(target_path)
    try:
        source.backup(target)
        integrity = target.execute("PRAGMA integrity_check").fetchone()
        if not integrity or integrity[0] != "ok":
            raise RuntimeError("SQLite 快照完整性检查失败")
    finally:
        target.close()
        source.close()


def _database_preview(path: Path) -> DatabasePreview:
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro&immutable=1", uri=True)
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if not integrity or integrity[0] != "ok":
            raise ValueError("SQLite 完整性检查失败")
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        }
        required_tables = {"users", "templates", "tasks", "task_runs"}
        missing = sorted(required_tables - tables)
        if missing:
            raise ValueError(f"不是完整的 QD2 数据库，缺少表: {', '.join(missing)}")

        user_columns = {row[1] for row in connection.execute("PRAGMA table_info(users)").fetchall()}
        if not {"username", "hashed_password", "role"}.issubset(user_columns):
            raise ValueError("users 表结构与 QD2 不兼容")

        return DatabasePreview(
            users=connection.execute("SELECT COUNT(*) FROM users").fetchone()[0],
            templates=connection.execute("SELECT COUNT(*) FROM templates").fetchone()[0],
            tasks=connection.execute("SELECT COUNT(*) FROM tasks").fetchone()[0],
            task_runs=connection.execute("SELECT COUNT(*) FROM task_runs").fetchone()[0],
            integrity="ok",
        )
    except sqlite3.DatabaseError as exc:
        raise ValueError("不是有效的 SQLite 数据库") from exc
    finally:
        connection.close()


def _pending_restore_path(database_path: Path) -> Path:
    return database_path.with_name(f"{database_path.name}.restore-pending")


async def _save_database_upload(file: UploadFile, directory: Path) -> Path:
    if not file.filename or not file.filename.lower().endswith(".db"):
        raise HTTPException(status_code=400, detail="请上传 .db 格式的 QD2 SQLite 数据库")
    directory.mkdir(parents=True, exist_ok=True)
    descriptor, temp_path = tempfile.mkstemp(prefix="qd2-restore-", suffix=".db", dir=directory)
    size = 0
    try:
        with os.fdopen(descriptor, "wb") as target:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_DATABASE_BACKUP_SIZE:
                    raise HTTPException(status_code=413, detail="数据库备份不能超过 1 GiB")
                target.write(chunk)
        return Path(temp_path)
    except Exception:
        _remove_snapshot(temp_path)
        raise


def apply_pending_database_restore(settings: QDServerSettings) -> Path | None:
    if settings.db.db_type != DBType.sqlite3:
        return None
    database_settings = settings.db.engine_settings
    if not isinstance(database_settings, Sqlite3Settings):
        return None
    database_path = database_settings.db_path
    pending_path = _pending_restore_path(database_path)
    if not pending_path.is_file():
        return None

    _database_preview(pending_path)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = database_path.with_name(f"{database_path.stem}.before-restore-{timestamp}{database_path.suffix}")
    moved: list[tuple[Path, Path]] = []
    try:
        for suffix in ("", "-wal", "-shm"):
            source = Path(f"{database_path}{suffix}")
            if not source.exists():
                continue
            target = Path(f"{backup_path}{suffix}")
            os.replace(source, target)
            moved.append((source, target))
        os.replace(pending_path, database_path)
    except Exception:
        for source, target in reversed(moved):
            if target.exists():
                os.replace(target, source)
        raise
    return backup_path


def _remove_snapshot(path: str) -> None:
    with contextlib.suppress(FileNotFoundError):
        os.unlink(path)


@router.get("/admin/database")
async def export_full_database(admin: Annotated[User, Depends(require_admin)]):
    del admin
    settings = get_settings()
    if settings.db.db_type != DBType.sqlite3:
        raise HTTPException(status_code=409, detail="完整 database.db 备份仅支持 SQLite；MySQL 请使用逻辑备份")
    database_settings = settings.db.engine_settings
    if not isinstance(database_settings, Sqlite3Settings):
        raise HTTPException(status_code=500, detail="SQLite 数据库配置无效")
    database_path = database_settings.db_path
    if not database_path.is_file():
        raise HTTPException(status_code=404, detail="SQLite 数据库文件不存在")

    descriptor, snapshot_path = tempfile.mkstemp(prefix="qd2-backup-", suffix=".db")
    os.close(descriptor)
    try:
        await asyncio.to_thread(_create_sqlite_snapshot, database_path, Path(snapshot_path))
    except Exception as exc:
        _remove_snapshot(snapshot_path)
        raise HTTPException(status_code=500, detail=f"创建数据库快照失败: {exc}") from exc

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return FileResponse(
        snapshot_path,
        media_type="application/vnd.sqlite3",
        filename=f"qd2-database-{timestamp}.db",
        headers={"Cache-Control": "no-store"},
        background=BackgroundTask(_remove_snapshot, snapshot_path),
    )


def _sqlite_database_path() -> Path:
    settings = get_settings()
    if settings.db.db_type != DBType.sqlite3:
        raise HTTPException(status_code=409, detail="完整 database.db 恢复仅支持 SQLite")
    database_settings = settings.db.engine_settings
    if not isinstance(database_settings, Sqlite3Settings):
        raise HTTPException(status_code=500, detail="SQLite 数据库配置无效")
    return database_settings.db_path


@router.post("/admin/database/preview", response_model=DatabasePreview)
async def preview_full_database_restore(
    file: Annotated[UploadFile, File()],
    admin: Annotated[User, Depends(require_admin)],
):
    del admin
    temp_path = await _save_database_upload(file, Path(tempfile.gettempdir()))
    try:
        return await asyncio.to_thread(_database_preview, temp_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        _remove_snapshot(str(temp_path))


@router.post("/admin/database/restore", response_model=DatabaseRestoreResult)
async def stage_full_database_restore(
    file: Annotated[UploadFile, File()],
    admin: Annotated[User, Depends(require_admin)],
    confirmation: Annotated[str, Form()] = "",
):
    del admin
    if confirmation != "RESTORE":
        raise HTTPException(status_code=400, detail="缺少完整数据库恢复确认")
    database_path = _sqlite_database_path()
    temp_path = await _save_database_upload(file, database_path.parent)
    try:
        preview = await asyncio.to_thread(_database_preview, temp_path)
        os.replace(temp_path, _pending_restore_path(database_path))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        if temp_path.exists():
            _remove_snapshot(str(temp_path))
    return DatabaseRestoreResult(staged=True, restart_required=True, preview=preview)
