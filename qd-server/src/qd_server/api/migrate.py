"""QD v1 data migration API routes.

Reads a real QD v1 database.db (SQLite):
  - table `user`:   username/email/role; userkey is AES-encrypted with global aes_key
  - table `tpl`:    har (AES-encrypted with userkey, umsgpack-packed), sitename, note, variables
  - table `task`:   tplid/userid, newontime schedule, retry_count, note

Decryption chain (from QD v1 libs/mcrypto.py + db/user.py):
  aes_key = sha256(AES_KEY env, default "binux")
  userkey = aes_decrypt(user.userkey, aes_key)           # umsgpack packb'd [ciphertext, iv]
  har     = aes_decrypt(tpl.har, userkey)                # ditto → msgpack → dict/list

Imported passwords CANNOT be migrated (v1 uses PBKDF2+AES chain); users are
created disabled with a random password and must be reset by the admin.

`newontime` is converted via convert_newontime() — see COMPATIBILITY.md.
"""

import json
import os
import secrets
import sqlite3
import tempfile
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from qd_server.middleware.auth import get_session, hash_password, require_admin
from qd_server.models.task import Task
from qd_server.models.template import Template
from qd_server.models.user import User

router = APIRouter()

MAX_DATABASE_SIZE = 100 * 1024 * 1024


class MigratePreview(BaseModel):
    """Preview of data to migrate."""
    templates: int
    users: int
    tasks: int
    decryptable: bool
    detail: str = ""


class MigrateResult(BaseModel):
    """Result of migration."""
    templates_imported: int
    tasks_imported: int
    users_imported: int
    errors: list[str]


def convert_newontime(newontime: dict, old_interval: Optional[int] = None) -> tuple[dict, dict]:
    """Convert QD v1 `newontime` config to QD2 schedule_config + execution_config.

    v1 format: {"sw": bool, "time": "HH:MM:SS", "randsw": bool, "tz1": int, "tz2": int}
      - sw: enable scheduled-time mode; time: daily run time
      - randsw: enable random delay window; tz1/tz2: random offset range (seconds)
    Returns (schedule_config, execution_config_patch).
    """
    if newontime and newontime.get("sw"):
        raw_time = str(newontime.get("time") or "00:10:10")
        parsed_time = None
        for time_format in ("%H:%M:%S", "%H:%M"):
            try:
                parsed_time = datetime.strptime(raw_time, time_format)
                break
            except ValueError:
                continue
        if parsed_time is None:
            raise ValueError(f"invalid newontime time: {raw_time!r}")

        exec_patch: dict = {}
        if newontime.get("randsw"):
            tz1 = int(newontime.get("tz1", 0) or 0)
            tz2 = int(newontime.get("tz2", 0) or 0)
            lo, hi = min(tz1, tz2), max(tz1, tz2)
            # QD2 delays forward only. Shift the daily trigger by the lower
            # offset so negative/cross-midnight windows retain exact timing.
            parsed_time += timedelta(seconds=lo)
            exec_patch = {
                "random_delay_min": 0,
                "random_delay_max": hi - lo,
            }

        schedule = {
            "schedule_type": "daily",
            "run_time": parsed_time.strftime("%H:%M:%S"),
        }
        return schedule, exec_patch

    if old_interval is not None and int(old_interval) > 0:
        return {"schedule_type": "interval", "interval_seconds": int(old_interval)}, {}
    return {"schedule_type": "once"}, {}


# --- v1 crypto helpers ---

def _v1_aes_key(aes_key_str: str) -> bytes:
    import hashlib

    return hashlib.sha256(aes_key_str.encode("utf-8")).digest()


def _v1_aes_decrypt(blob: bytes, key: bytes):
    """QD v1 aes_decrypt with packb (umsgpack [ciphertext, iv] envelope)."""
    import umsgpack
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import unpad

    word, iv = umsgpack.unpackb(blob)
    aes = AES.new(key, AES.MODE_CBC, iv)
    plain = unpad(aes.decrypt(word), AES.block_size)
    return umsgpack.unpackb(plain)


def _decode_deep(obj):
    """Recursively decode bytes keys/values from msgpack payloads."""
    if isinstance(obj, bytes):
        try:
            return obj.decode("utf-8")
        except UnicodeDecodeError:
            return obj
    if isinstance(obj, dict):
        return {_decode_deep(k): _decode_deep(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_decode_deep(v) for v in obj]
    return obj


def _load_v1_db(content: bytes) -> sqlite3.Connection:
    """Load an uploaded SQLite database into memory and remove its temp file.

    SQLite needs a filesystem path for broad Python 3.10 compatibility. Copying
    it into an in-memory connection lets us close and unlink the upload before
    any migration work, including on Windows.
    """
    if not content.startswith(b"SQLite format 3\x00"):
        raise ValueError("not a SQLite 3 database")

    tmp_path = ""
    source = None
    target = sqlite3.connect(":memory:")
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        source = sqlite3.connect(tmp_path)
        source.backup(target)
        target.row_factory = sqlite3.Row
        return target
    except Exception:
        target.close()
        raise
    finally:
        if source is not None:
            source.close()
        if tmp_path:
            os.unlink(tmp_path)


async def _read_database_upload(file: UploadFile) -> bytes:
    if not file.filename or not file.filename.lower().endswith(".db"):
        raise HTTPException(status_code=400, detail="请上传 .db 文件 (SQLite)")
    content = await file.read(MAX_DATABASE_SIZE + 1)
    if len(content) > MAX_DATABASE_SIZE:
        raise HTTPException(status_code=413, detail="数据库文件不能超过 100 MiB")
    return content


def _row_value(row: sqlite3.Row, *names: str, default=None):
    for name in names:
        if name in row.keys() and row[name] is not None:
            return row[name]
    return default


def _table_count(conn: sqlite3.Connection, table: str) -> int:
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608
    except sqlite3.OperationalError:
        return 0


@router.post("/preview", response_model=MigratePreview)
async def preview_v1_data(
    file: UploadFile = File(...),
    aes_key: str = Form("binux"),
    current_user: User = Depends(require_admin),
):
    """Preview QD v1 database contents and verify the AES key works."""
    content = await _read_database_upload(file)
    try:
        conn = _load_v1_db(content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"无法读取数据库文件: {e}") from e

    try:
        tpls = _table_count(conn, "tpl")
        users = _table_count(conn, "user")
        tasks = _table_count(conn, "task")

        # verify decryption chain on the first template
        decryptable = False
        detail = ""
        try:
            row = conn.execute(
                "SELECT t.har, u.userkey FROM tpl t JOIN user u ON t.userid = u.id "
                "WHERE t.har IS NOT NULL LIMIT 1"
            ).fetchone()
            if row:
                key = _v1_aes_key(aes_key)
                userkey = _v1_aes_decrypt(row["userkey"], key)
                _v1_aes_decrypt(row["har"], userkey)
                decryptable = True
            else:
                detail = "库中无加密模板可验证"
        except Exception as e:
            detail = f"解密失败 (AES_KEY 是否正确?): {e}"

        return MigratePreview(
            templates=tpls, users=users, tasks=tasks, decryptable=decryptable, detail=detail
        )
    finally:
        conn.close()


@router.post("/import", response_model=MigrateResult)
async def import_v1_data(
    file: UploadFile = File(...),
    aes_key: str = Form("binux"),
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Import QD v1 templates + tasks (and optionally users) into QD2.

    - Templates/tasks are decrypted with the v1 AES key chain and re-owned by
      the importing admin (v1 per-user ownership is preserved only for users
      that get imported).
    - v1 passwords cannot be recovered; imported users are created inactive
      with an unusable random password (admin resets via /api/admin).
    """
    content = await _read_database_upload(file)
    errors: list[str] = []
    templates_imported = 0
    tasks_imported = 0
    users_imported = 0
    tasks_to_schedule: list[Task] = []

    try:
        conn = _load_v1_db(content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"无法读取数据库文件: {e}") from e

    try:
        key = _v1_aes_key(aes_key)

        # --- users: v1 id -> qd2 id mapping ---
        v1_to_qd2_user: dict[int, int] = {}
        try:
            for row in conn.execute("SELECT * FROM user").fetchall():
                try:
                    async with session.begin_nested():
                        base_username = str(
                            _row_value(
                                row,
                                "nickname",
                                "username",
                                "email",
                                default=f"v1_user_{row['id']}",
                            )
                        )[:50]
                        username = base_username
                        suffix = 1
                        while (
                            await session.execute(select(User).where(User.username == username))
                        ).scalar_one_or_none():
                            marker = f"-v1-{row['id']}-{suffix}"
                            username = f"{base_username[: 50 - len(marker)]}{marker}"
                            suffix += 1

                        now = datetime.utcnow()
                        user = User(
                            username=username,
                            hashed_password=hash_password(secrets.token_urlsafe(24)),
                            email=_row_value(row, "email"),
                            role="user",
                            is_active=False,  # must be re-enabled + password reset by admin
                            created_at=now,
                            updated_at=now,
                        )
                        session.add(user)
                        await session.flush()
                        if user.id is None:
                            raise RuntimeError("database did not assign a user id")
                    v1_to_qd2_user[row["id"]] = user.id
                    users_imported += 1
                except Exception as e:
                    errors.append(f"导入用户 #{row['id']} 失败: {e}")
        except sqlite3.OperationalError as e:
            errors.append(f"user 表读取失败: {e}")

        # --- userkey cache ---
        userkeys: dict[int, bytes] = {}

        def get_userkey(userid: int) -> Optional[bytes]:
            if userid in userkeys:
                return userkeys[userid]
            row = conn.execute("SELECT userkey FROM user WHERE id = ?", (userid,)).fetchone()
            if not row:
                return None
            try:
                userkeys[userid] = _v1_aes_decrypt(row["userkey"], key)
                return userkeys[userid]
            except Exception:
                return None

        # --- templates: v1 tpl id -> qd2 template id ---
        v1_to_qd2_tpl: dict[int, int] = {}
        try:
            for row in conn.execute("SELECT * FROM tpl").fetchall():
                try:
                    if not row["har"]:
                        continue
                    userkey = get_userkey(row["userid"]) if row["userid"] else None
                    if userkey is None:
                        errors.append(f"模板 #{row['id']}: 无法解密 userkey, 跳过")
                        continue
                    har = _decode_deep(_v1_aes_decrypt(row["har"], userkey))

                    variables: dict = {}
                    try:
                        if row["variables"]:
                            var_names = json.loads(row["variables"])
                            if isinstance(var_names, list):
                                variables = {v: "" for v in var_names}
                    except (json.JSONDecodeError, TypeError):
                        pass

                    async with session.begin_nested():
                        owner_id = v1_to_qd2_user.get(row["userid"], current_user.id)
                        now = datetime.utcnow()
                        template = Template(
                            user_id=owner_id,
                            name=(row["sitename"] or f"v1 模板 #{row['id']}")[:100],
                            description=(row["note"] or "")[:500],
                            template_data=har,
                            variables=variables,
                            tags=["v1-import"],
                            created_at=now,
                            updated_at=now,
                        )
                        session.add(template)
                        await session.flush()
                        if template.id is None:
                            raise RuntimeError("database did not assign a template id")
                    v1_to_qd2_tpl[row["id"]] = template.id
                    templates_imported += 1
                except Exception as e:
                    errors.append(f"导入模板 #{row['id']} 失败: {e}")
        except sqlite3.OperationalError as e:
            errors.append(f"tpl 表读取失败: {e}")

        # --- tasks (with newontime conversion) ---
        try:
            for row in conn.execute("SELECT * FROM task").fetchall():
                try:
                    tpl_id = v1_to_qd2_tpl.get(row["tplid"])
                    if tpl_id is None:
                        continue  # template not imported → skip its tasks

                    newontime: dict = {}
                    try:
                        if row["newontime"]:
                            newontime = json.loads(row["newontime"])
                    except (json.JSONDecodeError, TypeError):
                        pass

                    old_interval = _row_value(row, "interval_seconds", "interval")
                    schedule, exec_patch = convert_newontime(newontime, old_interval)
                    execution_config = {
                        "retry_count": min(max(int(_row_value(row, "retry_count", default=0) or 0), 0), 10),
                        **exec_patch,
                    }

                    async with session.begin_nested():
                        owner_id = v1_to_qd2_user.get(row["userid"], current_user.id)
                        now = datetime.utcnow()
                        task = Task(
                            user_id=owner_id,
                            template_id=tpl_id,
                            name=(row["note"] or f"v1 任务 #{row['id']}")[:100],
                            description="imported from QD v1",
                            schedule_config=schedule,
                            variables={},
                            execution_config=execution_config,
                            status=(
                                "paused"
                                if _row_value(row, "disabled", default=False)
                                else "pending"
                            ),
                            created_at=now,
                            updated_at=now,
                        )
                        session.add(task)
                        await session.flush()
                    tasks_to_schedule.append(task)
                    tasks_imported += 1
                except Exception as e:
                    errors.append(f"导入任务 #{row['id']} 失败: {e}")
        except sqlite3.OperationalError as e:
            errors.append(f"task 表读取失败: {e}")

        await session.commit()

        from qd_server.services.scheduler import scheduler

        for task in tasks_to_schedule:
            if task.user_id != current_user.id or task.status in ("paused", "disabled"):
                continue
            try:
                scheduler.add_task(task)
            except Exception as e:
                errors.append(f"注册任务 #{task.id} 调度失败: {e}")

        return MigrateResult(
            templates_imported=templates_imported,
            tasks_imported=tasks_imported,
            users_imported=users_imported,
            errors=errors,
        )
    finally:
        conn.close()
