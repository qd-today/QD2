"""QD v1 data migration API routes."""

import json
import sqlite3
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from qd_server.middleware.auth import get_current_user, get_session, require_admin
from qd_server.models.user import User

router = APIRouter()


class MigratePreview(BaseModel):
    """Preview of data to migrate."""
    templates: int
    users: int
    cookies: int


class MigrateResult(BaseModel):
    """Result of migration."""
    templates_imported: int
    users_imported: int
    errors: list[str]


@router.post("/preview", response_model=MigratePreview)
async def preview_v1_data(
    file: UploadFile = File(...),
    current_user: User = Depends(require_admin),
):
    """Preview QD v1 database contents before migration.

    Upload a QD v1 database.db file to see what data will be imported.
    """
    if not file.filename or not file.filename.endswith('.db'):
        raise HTTPException(status_code=400, detail="请上传 .db 文件 (SQLite)")

    content = await file.read()

    try:
        # Write to temp file and read
        import tempfile
        import os

        with tempfile.NamedTemporaryFile(delete=False, suffix='.db') as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        try:
            conn = sqlite3.connect(tmp_path)
            cursor = conn.cursor()

            # Count templates
            try:
                cursor.execute("SELECT COUNT(*) FROM templates")
                templates = cursor.fetchone()[0]
            except sqlite3.OperationalError:
                templates = 0

            # Count users
            try:
                cursor.execute("SELECT COUNT(*) FROM users")
                users = cursor.fetchone()[0]
            except sqlite3.OperationalError:
                users = 0

            # Count cookies
            try:
                cursor.execute("SELECT COUNT(*) FROM cookies")
                cookies = cursor.fetchone()[0]
            except sqlite3.OperationalError:
                cookies = 0

            conn.close()

            return MigratePreview(
                templates=templates,
                users=users,
                cookies=cookies,
            )
        finally:
            os.unlink(tmp_path)

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"无法读取数据库文件: {e}")


@router.post("/import", response_model=MigrateResult)
async def import_v1_data(
    file: UploadFile = File(...),
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Import QD v1 data into QD2.

    Upload a QD v1 database.db file to import templates and user data.
    """
    if not file.filename or not file.filename.endswith('.db'):
        raise HTTPException(status_code=400, detail="请上传 .db 文件 (SQLite)")

    content = await file.read()
    errors = []
    templates_imported = 0
    users_imported = 0

    try:
        import tempfile
        import os
        from datetime import datetime

        with tempfile.NamedTemporaryFile(delete=False, suffix='.db') as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        try:
            conn = sqlite3.connect(tmp_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Import users (skip duplicates)
            try:
                cursor.execute("SELECT * FROM users")
                for row in cursor.fetchall():
                    try:
                        from qd_server.models.user import User as UserModel
                        from qd_server.middleware.auth import hash_password
                        from sqlmodel import select

                        # Check if user exists
                        result = await session.execute(
                            select(UserModel).where(UserModel.username == row["username"])
                        )
                        if result.scalar_one_or_none():
                            continue

                        user = UserModel(
                            username=row["username"],
                            hashed_password=row.get("password", ""),
                            email=row.get("email"),
                            role="user",
                            is_active=True,
                        )
                        session.add(user)
                        users_imported += 1
                    except Exception as e:
                        errors.append(f"导入用户失败: {e}")
            except sqlite3.OperationalError:
                pass

            # Import templates
            try:
                cursor.execute("SELECT * FROM template")
                for row in cursor.fetchall():
                    try:
                        from qd_server.models.template import Template
                        from sqlmodel import select

                        # Parse template data
                        template_data = {}
                        try:
                            raw = row.get("har", "") or row.get("template", "")
                            if raw:
                                template_data = json.loads(raw)
                        except (json.JSONDecodeError, TypeError):
                            pass

                        # Get owner user
                        result = await session.execute(
                            select(UserModel).limit(1)
                        )
                        owner = result.scalar_one_or_none()
                        if not owner:
                            continue

                        now = datetime.utcnow()
                        template = Template(
                            user_id=owner.id,
                            name=row.get("name", f"Imported #{row.get('id', '')}"),
                            description=row.get("desc", ""),
                            template_data=template_data,
                            variables={},
                            tags=[],
                            created_at=now,
                            updated_at=now,
                        )
                        session.add(template)
                        templates_imported += 1
                    except Exception as e:
                        errors.append(f"导入模板失败: {e}")
            except sqlite3.OperationalError:
                pass

            conn.close()
            await session.commit()

        finally:
            os.unlink(tmp_path)

        return MigrateResult(
            templates_imported=templates_imported,
            users_imported=users_imported,
            errors=errors,
        )

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"迁移失败: {e}")
