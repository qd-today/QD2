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

import base64
import json
import os
import secrets
import sqlite3
import tempfile
from copy import deepcopy
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urlsplit, urlunsplit

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from qd_core.client.har import HARParser
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from qd_server.middleware.auth import get_session, hash_password, require_admin
from qd_server.models.notepad import Notepad
from qd_server.models.notification import Notification
from qd_server.models.task import Task
from qd_server.models.task_group import TaskGroup
from qd_server.models.template import Template
from qd_server.models.user import User
from qd_server.services.encryption import protect_dict, protect_list

router = APIRouter()

MAX_DATABASE_SIZE = 100 * 1024 * 1024


class MigratePreview(BaseModel):
    """Preview of data to migrate."""
    templates: int
    public_templates: int
    users: int
    tasks: int
    task_groups: int
    notifications: int
    notepads: int
    decryptable: bool
    detail: str = ""


class MigrateResult(BaseModel):
    """Result of migration."""
    templates_imported: int
    tasks_imported: int
    task_groups_imported: int
    users_imported: int
    notifications_imported: int
    notepads_imported: int
    errors: list[str]


def convert_newontime(
    newontime: dict,
    old_interval: Optional[int] = None,
    old_ontimeflg: bool = False,
    old_ontime: str | None = None,
) -> tuple[dict, dict]:
    """Convert QD v1 `newontime` config to QD2 schedule_config + execution_config.

    v1 format: {"sw": bool, "time": "HH:MM:SS", "randsw": bool, "tz1": int, "tz2": int}
      - sw: enable scheduled-time mode; time: daily run time
      - randsw: enable random delay window; tz1/tz2: random offset range (seconds)
    Returns (schedule_config, execution_config_patch).
    """
    if newontime and newontime.get("sw"):
        mode = str(newontime.get("mode") or "daily").lower()
        random_enabled = bool(newontime.get("randsw"))
        tz1 = int(newontime.get("tz1", 0) or 0)
        tz2 = int(newontime.get("tz2", 0) or 0)
        lo, hi = min(tz1, tz2), max(tz1, tz2)

        if mode == "cron" and newontime.get("cron_val"):
            exec_patch = {}
            if random_enabled:
                exec_patch = {
                    "random_delay_min": max(0, lo),
                    "random_delay_max": max(0, hi),
                }
            return {
                "schedule_type": "cron",
                "cron_expression": str(newontime["cron_val"]).strip(),
            }, exec_patch

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
        if random_enabled:
            parsed_time += timedelta(seconds=lo)
            exec_patch = {
                "random_delay_min": 0,
                "random_delay_max": hi - lo,
            }

        if mode == "ontime" and newontime.get("date"):
            start_date = datetime.strptime(str(newontime["date"]), "%Y-%m-%d")
            return {
                "schedule_type": "daily",
                "run_time": parsed_time.strftime("%H:%M:%S"),
                "start_date": start_date.date().isoformat(),
            }, exec_patch

        return {
            "schedule_type": "daily",
            "run_time": parsed_time.strftime("%H:%M:%S"),
        }, exec_patch

    if old_ontimeflg and old_ontime:
        raw_time = str(old_ontime)
        for time_format in ("%H:%M:%S", "%H:%M"):
            try:
                parsed_time = datetime.strptime(raw_time, time_format)
                return {
                    "schedule_type": "daily",
                    "run_time": parsed_time.strftime("%H:%M:%S"),
                }, {}
            except ValueError:
                continue
        raise ValueError(f"invalid legacy ontime: {raw_time!r}")

    if old_interval is not None and int(old_interval) > 0:
        return {"schedule_type": "interval", "interval_seconds": int(old_interval)}, {}
    return {"schedule_type": "once"}, {}


# --- v1 crypto helpers ---

def _v1_aes_key(aes_key_str: str) -> bytes:
    import hashlib

    return hashlib.sha256(aes_key_str.encode("utf-8")).digest()


def _v1_aes_decrypt(blob: bytes, key: bytes):
    """Decrypt QD v1's zero-padded msgpack [ciphertext, iv] envelope."""
    import umsgpack
    from Crypto.Cipher import AES

    word, iv = umsgpack.unpackb(blob)
    aes = AES.new(key, AES.MODE_CBC, iv)
    plain = aes.decrypt(word).rstrip(b"\x00")
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


def _json_safe_deep(obj):
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    if isinstance(obj, dict):
        return {str(_json_safe_deep(key)): _json_safe_deep(value) for key, value in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe_deep(value) for value in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)


def _v1_task_payload(row: sqlite3.Row, field: str, userkey: bytes | None, default):
    if userkey is None:
        return default
    value = _row_value(row, field)
    if value in (None, "", b""):
        return default
    raw = value.encode() if isinstance(value, str) else bytes(value)
    return _json_safe_deep(_decode_deep(_v1_aes_decrypt(raw, userkey)))


def _int_or_default(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


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


def _normalize_v1_template_data(har: dict | list, name: str, description: str) -> dict:
    normalized_har = deepcopy(har)
    if isinstance(normalized_har, dict):
        entries = normalized_har.get("log", {}).get("entries", [])
    else:
        entries = normalized_har

    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("request"), dict):
            continue
        request = entry["request"]
        for field in ("method", "url", "httpVersion"):
            if field in request and not isinstance(request[field], str):
                request[field] = _v1_text_value(request[field])
        for collection_name in ("headers", "queryString", "cookies"):
            for item in request.get(collection_name, []) or []:
                if not isinstance(item, dict):
                    continue
                for field in ("name", "value"):
                    if field in item and not isinstance(item[field], str):
                        item[field] = _v1_text_value(item[field])
        post_data = request.get("postData")
        if isinstance(post_data, dict):
            if not post_data.get("mimeType"):
                post_data["mimeType"] = next(
                    (
                        header["value"]
                        for header in request.get("headers", []) or []
                        if isinstance(header, dict)
                        and str(header.get("name", "")).lower() == "content-type"
                    ),
                    "application/x-www-form-urlencoded",
                )
            if "text" in post_data and not isinstance(post_data["text"], str):
                post_data["text"] = _v1_text_value(post_data["text"])

    parsed = HARParser.parse_dict(normalized_har)
    data = parsed.model_dump(mode="json", exclude_none=True, by_alias=True)
    data["name"] = name
    data["description"] = description

    if isinstance(har, dict):
        source_entries = [
            entry
            for entry in har.get("log", {}).get("entries", [])
            if isinstance(entry, dict) and entry.get("request")
        ]
    else:
        source_entries = [
            entry for entry in har if isinstance(entry, dict) and entry.get("request")
        ]

    for request, entry in zip(data.get("requests", []), source_entries, strict=False):
        raw_request = entry.get("request", {})
        comment = entry.get("comment") or raw_request.get("comment")
        if comment:
            request["_comment"] = comment
        resource_type = (
            entry.get("_resourceType")
            or entry.get("resourceType")
            or raw_request.get("_resourceType")
        )
        if resource_type:
            request["_resourceType"] = resource_type
        response = entry.get("response") or {}
        response_headers = response.get("headers") or []
        request["_hasResponseSetCookie"] = bool(
            response.get("cookies")
            or any(
                str(header.get("name", "")).lower() == "set-cookie"
                for header in response_headers
                if isinstance(header, dict)
            )
        )
    return data


def _v1_text_value(value) -> str:
    if isinstance(value, list):
        return "".join(_v1_text_value(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if value is None:
        return ""
    return str(value)


def _v1_notification_channels(row: sqlite3.Row) -> list[dict]:
    try:
        notice_flags = int(_row_value(row, "noticeflg", default=0) or 0)
    except (TypeError, ValueError):
        notice_flags = 0
    on_success = bool(notice_flags & 2)
    on_failure = bool(notice_flags & 1)

    failure_threshold = 1
    try:
        logtime = json.loads(_row_value(row, "logtime", default="{}") or "{}")
        if isinstance(logtime, dict):
            failure_threshold = int(logtime.get("ErrTolerateCnt", 0) or 0) + 1
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    failure_threshold = min(max(failure_threshold, 1), 100)

    channels: list[dict] = []

    def add(name: str, notification_type: str, config: dict, enabled_flag: int):
        if config and all(value not in (None, "") for value in config.values()):
            config = {**config, "failure_threshold": failure_threshold}
            channels.append(
                {
                    "name": name,
                    "notification_type": notification_type,
                    "config": config,
                    "enabled": bool(notice_flags & enabled_flag),
                    "on_success": on_success,
                    "on_failure": on_failure,
                }
            )

    sendkey = str(_row_value(row, "skey", default="") or "").strip()
    if sendkey:
        add("QD v1 Server酱", "serverchan", {"sendkey": sendkey}, 0x20)

    bark_url = str(_row_value(row, "barkurl", default="") or "").strip()
    if bark_url:
        parsed = urlsplit(bark_url)
        path_parts = [part for part in parsed.path.split("/") if part]
        if parsed.scheme and parsed.netloc and path_parts:
            server_path = "/" + "/".join(path_parts[:-1]) if len(path_parts) > 1 else ""
            server = urlunsplit((parsed.scheme, parsed.netloc, server_path, "", ""))
            add(
                "QD v1 Bark",
                "bark",
                {"server": server, "device_key": path_parts[-1]},
                0x40,
            )

    wxpusher = str(_row_value(row, "wxpusher", default="") or "").strip()
    if wxpusher:
        app_token, separator, uids = wxpusher.partition(";")
        if separator:
            add(
                "QD v1 Wxpusher",
                "wxpusher",
                {"app_token": app_token.strip(), "uids": uids.strip()},
                0x10,
            )

    diy_pusher = str(_row_value(row, "diypusher", default="") or "").strip()
    if diy_pusher.startswith(("http://", "https://")):
        add(
            "QD v1 自定义推送",
            "webhook",
            {"url": diy_pusher, "method": "POST"},
            0x100,
        )

    wecom_app = str(_row_value(row, "qywx_token", default="") or "").strip()
    if wecom_app:
        parts = (wecom_app.split(";", 3) + ["", "", "", ""])[:4]
        corp_id, agent_id, corp_secret, touser = (part.strip() for part in parts)
        add(
            "QD v1 企业微信应用",
            "wecom_app",
            {
                "corp_id": corp_id,
                "agent_id": int(agent_id) if agent_id.isdigit() else agent_id,
                "corp_secret": corp_secret,
                "touser": touser or "@all",
            },
            0x200,
        )

    wecom_webhook = str(_row_value(row, "qywx_webhook", default="") or "").strip()
    if wecom_webhook:
        config = (
            {"url": wecom_webhook}
            if wecom_webhook.startswith(("http://", "https://"))
            else {"key": wecom_webhook}
        )
        add("QD v1 企业微信机器人", "wecom", config, 0x1000)

    telegram = str(_row_value(row, "tg_token", default="") or "").strip()
    if telegram:
        parts = telegram.split(";", 2)
        if len(parts) >= 2:
            config = {"bot_token": parts[0].strip(), "chat_id": parts[1].strip()}
            if len(parts) == 3 and parts[2].strip():
                config["api_host"] = parts[2].strip()
            add("QD v1 Telegram", "telegram", config, 0x400)

    dingtalk = str(_row_value(row, "dingding_token", default="") or "").strip()
    if dingtalk:
        access_token, _, secret = dingtalk.partition(";")
        config = {"access_token": access_token.strip()}
        if secret.strip():
            config["secret"] = secret.strip()
        add("QD v1 钉钉", "dingtalk", config, 0x800)

    return channels


def _table_count(conn: sqlite3.Connection, table: str) -> int:
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608
    except sqlite3.OperationalError:
        return 0


def _referenced_public_templates(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    try:
        return conn.execute(
            "SELECT DISTINCT p.id AS pubtpl_id, t.userid AS userid, p.name, "
            "p.filename, p.comments, p.content "
            "FROM task t "
            "LEFT JOIN tpl own_tpl ON own_tpl.id = t.tplid "
            "JOIN pubtpl p ON p.id = t.tplid "
            "WHERE own_tpl.id IS NULL"
        ).fetchall()
    except sqlite3.OperationalError:
        return []


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
        public_tpls = len(_referenced_public_templates(conn))
        users = _table_count(conn, "user")
        tasks = _table_count(conn, "task")
        task_groups = 0
        try:
            task_groups = conn.execute(
                "SELECT COUNT(*) FROM ("
                "SELECT DISTINCT userid, _groups FROM task "
                "WHERE _groups IS NOT NULL AND TRIM(_groups) NOT IN ('', 'None', 'null')"
                ")"
            ).fetchone()[0]
        except sqlite3.OperationalError:
            pass
        notepads = _table_count(conn, "notepad")
        notifications = 0
        try:
            notifications = sum(
                len(_v1_notification_channels(row))
                for row in conn.execute("SELECT * FROM user").fetchall()
            )
        except sqlite3.OperationalError:
            pass

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
            templates=tpls,
            public_templates=public_tpls,
            users=users,
            tasks=tasks,
            task_groups=task_groups,
            notifications=notifications,
            notepads=notepads,
            decryptable=decryptable,
            detail=detail,
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
    task_groups_imported = 0
    users_imported = 0
    notifications_imported = 0
    notepads_imported = 0
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

        # --- user notification channels ---
        try:
            for row in conn.execute("SELECT * FROM user").fetchall():
                owner_id = v1_to_qd2_user.get(row["id"], current_user.id)
                for channel in _v1_notification_channels(row):
                    try:
                        async with session.begin_nested():
                            channel = dict(channel)
                            channel["config"] = protect_dict(
                                channel.get("config", {}),
                                "notification.config",
                            )
                            session.add(
                                Notification(
                                    user_id=owner_id,
                                    task_id=None,
                                    created_at=datetime.utcnow(),
                                    updated_at=datetime.utcnow(),
                                    **channel,
                                )
                            )
                            await session.flush()
                        notifications_imported += 1
                    except Exception as e:
                        errors.append(
                            f"导入用户 #{row['id']} 通知渠道 {channel['name']} 失败: {e}"
                        )
        except sqlite3.OperationalError as e:
            errors.append(f"通知配置读取失败: {e}")

        # --- notepads ---
        try:
            for row in conn.execute("SELECT * FROM notepad").fetchall():
                try:
                    async with session.begin_nested():
                        owner_id = v1_to_qd2_user.get(row["userid"], current_user.id)
                        notepad_id = _row_value(row, "notepadid", "id", default=row["id"])
                        now = datetime.utcnow()
                        session.add(
                            Notepad(
                                user_id=owner_id,
                                title=f"QD v1 记事本 #{notepad_id}",
                                content=str(_row_value(row, "content", default="") or "")[:50000],
                                category="QD v1",
                                tags="v1-import",
                                sort_order=int(notepad_id or 0),
                                created_at=now,
                                updated_at=now,
                            )
                        )
                        await session.flush()
                    notepads_imported += 1
                except Exception as e:
                    errors.append(f"导入记事本 #{row['id']} 失败: {e}")
        except sqlite3.OperationalError:
            pass

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
        v1_task_template_names: dict[tuple[int, int], str] = {}
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
                    template_name = (row["sitename"] or f"v1 模板 #{row['id']}")[:100]
                    description = (row["note"] or "")[:500]
                    template_data = _normalize_v1_template_data(
                        har, template_name, description
                    )

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
                            name=template_name,
                            description=description,
                            template_data=template_data,
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
                    v1_task_template_names[(row["id"], row["userid"])] = template_name
                    templates_imported += 1
                except Exception as e:
                    errors.append(f"导入模板 #{row['id']} 失败: {e}")
        except sqlite3.OperationalError as e:
            errors.append(f"tpl 表读取失败: {e}")

        # --- public templates referenced by tasks: one private copy per owner ---
        v1_public_to_qd2_tpl: dict[tuple[int, int], int] = {}
        for row in _referenced_public_templates(conn):
            try:
                decoded = base64.b64decode(str(row["content"]).encode("ascii"))
                har = json.loads(decoded.decode("utf-8"))
                template_name = (
                    row["name"] or row["filename"] or f"v1 公共模板 #{row['pubtpl_id']}"
                )[:100]
                description = (row["comments"] or "")[:500]
                template_data = _normalize_v1_template_data(
                    har, template_name, description
                )
                async with session.begin_nested():
                    owner_id = v1_to_qd2_user.get(row["userid"], current_user.id)
                    now = datetime.utcnow()
                    template = Template(
                        user_id=owner_id,
                        name=template_name,
                        description=description,
                        template_data=template_data,
                        variables={},
                        tags=["v1-import", "v1-public-template"],
                        created_at=now,
                        updated_at=now,
                    )
                    session.add(template)
                    await session.flush()
                    if template.id is None:
                        raise RuntimeError("database did not assign a template id")
                v1_public_to_qd2_tpl[(row["pubtpl_id"], row["userid"])] = template.id
                v1_task_template_names[(row["pubtpl_id"], row["userid"])] = template_name
                templates_imported += 1
            except Exception as e:
                errors.append(
                    f"导入公共模板 #{row['pubtpl_id']} (用户 #{row['userid']}) 失败: {e}"
                )

        # --- task groups ---
        v1_task_groups: dict[tuple[int, str], int] = {}
        try:
            group_rows = conn.execute(
                "SELECT DISTINCT userid, _groups AS group_name FROM task "
                "WHERE _groups IS NOT NULL AND TRIM(_groups) NOT IN ('', 'None', 'null')"
            ).fetchall()
            for row in group_rows:
                try:
                    group_name = str(row["group_name"]).strip()[:100]
                    owner_id = v1_to_qd2_user.get(row["userid"], current_user.id)
                    async with session.begin_nested():
                        group = TaskGroup(
                            user_id=owner_id,
                            name=group_name,
                            description="imported from QD v1",
                        )
                        session.add(group)
                        await session.flush()
                        if group.id is None:
                            raise RuntimeError("database did not assign a task group id")
                    v1_task_groups[(row["userid"], group_name)] = group.id
                    task_groups_imported += 1
                except Exception as e:
                    errors.append(f"导入任务分组 {row['group_name']} 失败: {e}")
        except sqlite3.OperationalError:
            pass

        # --- tasks (variables, cookies, scheduling, and execution config) ---
        try:
            for row in conn.execute("SELECT * FROM task").fetchall():
                try:
                    tpl_id = v1_to_qd2_tpl.get(row["tplid"])
                    if tpl_id is None:
                        tpl_id = v1_public_to_qd2_tpl.get((row["tplid"], row["userid"]))
                    if tpl_id is None:
                        errors.append(
                            f"任务 #{row['id']}: 模板 #{row['tplid']} 未迁移，跳过"
                        )
                        continue

                    newontime: dict = {}
                    try:
                        if row["newontime"]:
                            newontime = json.loads(row["newontime"])
                    except (json.JSONDecodeError, TypeError):
                        pass

                    old_interval = _row_value(row, "interval_seconds", "interval")
                    schedule, exec_patch = convert_newontime(
                        newontime,
                        old_interval,
                        bool(_row_value(row, "ontimeflg", default=False)),
                        _row_value(row, "ontime"),
                    )
                    userkey = get_userkey(row["userid"])
                    init_env = _v1_task_payload(row, "init_env", userkey, {})
                    variables = dict(init_env) if isinstance(init_env, dict) else {}
                    proxy = str(variables.pop("_proxy", "") or "")
                    env_retry_count = variables.pop("retry_count", None)
                    env_retry_interval = variables.pop("retry_interval", None)
                    variables.pop("__log__", None)

                    retry_count = _int_or_default(
                        _row_value(row, "retry_count", default=env_retry_count),
                        _int_or_default(env_retry_count, 0),
                    )
                    retry_interval = _int_or_default(
                        _row_value(row, "retry_interval", default=env_retry_interval),
                        _int_or_default(env_retry_interval, 30),
                    )
                    execution_config = {
                        "retry_count": min(max(retry_count, 0), 10),
                        "retry_interval_seconds": min(max(retry_interval, 0), 86400),
                        "proxy": proxy,
                        **exec_patch,
                    }
                    push_enabled = True
                    try:
                        pushsw = json.loads(_row_value(row, "pushsw", default="{}") or "{}")
                        if isinstance(pushsw, dict):
                            push_enabled = bool(pushsw.get("pushen", True))
                    except (json.JSONDecodeError, TypeError):
                        pass
                    execution_config.update(
                        {
                            "notify_on_success": push_enabled,
                            "notify_on_failure": push_enabled,
                        }
                    )

                    cookie_session = _v1_task_payload(row, "session", userkey, [])
                    if not isinstance(cookie_session, list):
                        cookie_session = []

                    group_name = str(_row_value(row, "_groups", default="") or "").strip()
                    group_id = v1_task_groups.get((row["userid"], group_name))
                    task_name = v1_task_template_names.get(
                        (row["tplid"], row["userid"]),
                        f"v1 任务 #{row['id']}",
                    )

                    async with session.begin_nested():
                        owner_id = v1_to_qd2_user.get(row["userid"], current_user.id)
                        now = datetime.utcnow()
                        task = Task(
                            user_id=owner_id,
                            template_id=tpl_id,
                            group_id=group_id,
                            name=task_name[:100],
                            description=(row["note"] or "")[:500],
                            schedule_config=schedule,
                            variables=protect_dict(variables, "task.variables"),
                            execution_config=execution_config,
                            cookie_session=protect_list(cookie_session, "task.cookie_session"),
                            status=(
                                "disabled"
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
            task_groups_imported=task_groups_imported,
            users_imported=users_imported,
            notifications_imported=notifications_imported,
            notepads_imported=notepads_imported,
            errors=errors,
        )
    finally:
        conn.close()
