"""Admin API — user management + system settings (admin only)."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from qd_server.middleware.auth import get_session, hash_password, require_admin
from qd_server.models.system_setting import SystemSetting
from qd_server.models.task import Task, TaskRun
from qd_server.models.template import Template
from qd_server.models.user import User

router = APIRouter()


# --- Schemas ---

class AdminUserResponse(BaseModel):
    id: int
    username: str
    email: Optional[str]
    role: str
    is_active: bool
    display_name: Optional[str]
    last_login: Optional[datetime]
    created_at: datetime
    task_count: int = 0
    template_count: int = 0


class AdminUserUpdate(BaseModel):
    role: Optional[str] = None  # admin / user
    is_active: Optional[bool] = None
    email: Optional[str] = None
    display_name: Optional[str] = None


class ResetPasswordRequest(BaseModel):
    new_password: str


class SettingsResponse(BaseModel):
    registration_enabled: bool = True
    max_tasks_per_user: int = 0  # 0 = unlimited


class SettingsUpdate(BaseModel):
    registration_enabled: Optional[bool] = None
    max_tasks_per_user: Optional[int] = None


SETTINGS_KEY = "system"
DEFAULT_SETTINGS = {"registration_enabled": True, "max_tasks_per_user": 0}


async def get_system_settings(session: AsyncSession) -> dict:
    """Read system settings (with defaults)."""
    result = await session.execute(select(SystemSetting).where(SystemSetting.key == SETTINGS_KEY))
    row = result.scalar_one_or_none()
    merged = dict(DEFAULT_SETTINGS)
    if row and isinstance(row.value, dict):
        merged.update(row.value)
    return merged


# --- User management ---

@router.get("/users", response_model=list[AdminUserResponse])
async def list_users(
    search: Optional[str] = Query(None),
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """List all users with resource counts."""
    query = select(User).order_by(col(User.id))
    if search:
        query = query.where(col(User.username).contains(search))
    result = await session.execute(query)
    users = result.scalars().all()

    # counts
    task_counts: dict[int, int] = {}
    tpl_counts: dict[int, int] = {}
    tc = await session.execute(select(Task.user_id, func.count()).group_by(Task.user_id))
    for uid, cnt in tc.all():
        task_counts[uid] = cnt
    pc = await session.execute(select(Template.user_id, func.count()).group_by(Template.user_id))
    for uid, cnt in pc.all():
        tpl_counts[uid] = cnt

    return [
        AdminUserResponse(
            id=u.id,
            username=u.username,
            email=u.email,
            role=u.role,
            is_active=u.is_active,
            display_name=u.display_name,
            last_login=u.last_login,
            created_at=u.created_at,
            task_count=task_counts.get(u.id, 0),
            template_count=tpl_counts.get(u.id, 0),
        )
        for u in users
    ]


async def _get_user(user_id: int, session: AsyncSession) -> User:
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.put("/users/{user_id}", response_model=AdminUserResponse)
async def update_user(
    user_id: int,
    request: AdminUserUpdate,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Update a user's role/status/profile."""
    user = await _get_user(user_id, session)

    if request.role is not None:
        if request.role not in ("admin", "user"):
            raise HTTPException(status_code=422, detail="role must be 'admin' or 'user'")
        # prevent removing the last admin
        if user.role == "admin" and request.role != "admin":
            result = await session.execute(select(func.count()).where(User.role == "admin", User.is_active == True))  # noqa: E712
            admin_count = result.scalar_one()
            if admin_count <= 1:
                raise HTTPException(status_code=409, detail="Cannot demote the last admin")
        user.role = request.role

    if request.is_active is not None:
        # prevent deactivating the last admin
        if user.role == "admin" and not request.is_active:
            result = await session.execute(select(func.count()).where(User.role == "admin", User.is_active == True))  # noqa: E712
            admin_count = result.scalar_one()
            if admin_count <= 1:
                raise HTTPException(status_code=409, detail="Cannot deactivate the last admin")
        user.is_active = request.is_active

    if request.email is not None:
        user.email = request.email
    if request.display_name is not None:
        user.display_name = request.display_name

    user.updated_at = datetime.utcnow()
    session.add(user)
    await session.commit()
    await session.refresh(user)

    return AdminUserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        display_name=user.display_name,
        last_login=user.last_login,
        created_at=user.created_at,
    )


@router.post("/users/{user_id}/reset-password")
async def reset_password(
    user_id: int,
    request: ResetPasswordRequest,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Reset a user's password."""
    if len(request.new_password) < 6:
        raise HTTPException(status_code=422, detail="Password must be at least 6 characters")
    user = await _get_user(user_id, session)
    user.hashed_password = hash_password(request.new_password)
    user.updated_at = datetime.utcnow()
    session.add(user)
    await session.commit()
    return {"ok": True, "user_id": user_id}


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Delete a user and all their resources."""
    if user_id == admin.id:
        raise HTTPException(status_code=409, detail="Cannot delete yourself")

    user = await _get_user(user_id, session)
    if user.role == "admin":
        result = await session.execute(select(func.count()).where(User.role == "admin"))
        if result.scalar_one() <= 1:
            raise HTTPException(status_code=409, detail="Cannot delete the last admin")

    # cascade: delete user's resources
    from qd_server.models.notepad import Notepad
    from qd_server.models.notification import Notification
    from qd_server.models.task_group import TaskGroup
    from qd_server.models.template_source import TemplateSource

    for model in (TaskRun, Task, Template, TemplateSource, TaskGroup, Notification, Notepad):
        rows = await session.execute(select(model).where(model.user_id == user_id))
        for row in rows.scalars().all():
            await session.delete(row)

    await session.delete(user)
    await session.commit()


# --- System settings ---

@router.get("/settings", response_model=SettingsResponse)
async def read_settings(
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Read system settings."""
    merged = await get_system_settings(session)
    return SettingsResponse(**merged)


@router.put("/settings", response_model=SettingsResponse)
async def update_settings(
    request: SettingsUpdate,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Update system settings."""
    result = await session.execute(select(SystemSetting).where(SystemSetting.key == SETTINGS_KEY))
    row = result.scalar_one_or_none()
    now = datetime.utcnow()

    if row is None:
        row = SystemSetting(key=SETTINGS_KEY, value=dict(DEFAULT_SETTINGS), created_at=now, updated_at=now)

    value = dict(row.value or {})
    update = request.model_dump(exclude_unset=True, exclude_none=True)
    value.update(update)
    row.value = value
    row.updated_at = now
    session.add(row)
    await session.commit()

    merged = dict(DEFAULT_SETTINGS)
    merged.update(value)
    return SettingsResponse(**merged)


# --- Overview stats ---

@router.get("/stats")
async def admin_stats(
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Global stats for the admin dashboard."""
    users = (await session.execute(select(func.count()).select_from(User))).scalar_one()
    tasks = (await session.execute(select(func.count()).select_from(Task))).scalar_one()
    templates = (await session.execute(select(func.count()).select_from(Template))).scalar_one()
    runs = (await session.execute(select(func.count()).select_from(TaskRun))).scalar_one()
    failed_runs = (
        await session.execute(select(func.count()).select_from(TaskRun).where(TaskRun.status == "failed"))
    ).scalar_one()

    return {
        "users": users,
        "tasks": tasks,
        "templates": templates,
        "runs": runs,
        "failed_runs": failed_runs,
    }
