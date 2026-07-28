"""Task management API routes."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import delete as sql_delete
from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from qd_server.middleware.auth import get_current_user, get_session
from qd_server.models.task import Task, TaskRun
from qd_server.models.task_group import TaskGroup
from qd_server.models.template import Template
from qd_server.models.user import User

router = APIRouter()


# --- Request/Response schemas ---

class TaskCreate(BaseModel):
    template_id: int
    name: str
    description: Optional[str] = ""
    schedule_config: dict = {}
    variables: dict = {}
    execution_config: dict = {}
    group_id: Optional[int] = None


class TaskUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    schedule_config: Optional[dict] = None
    variables: Optional[dict] = None
    execution_config: Optional[dict] = None
    status: Optional[str] = None  # pause, resume
    group_id: Optional[int] = None


class TaskResponse(BaseModel):
    id: int
    template_id: int
    name: str
    description: Optional[str]
    schedule_config: dict
    status: str
    variables: dict
    execution_config: dict = {}
    group_id: Optional[int]
    next_run_at: Optional[datetime]
    run_count: int
    last_run_at: Optional[datetime]
    last_status: Optional[str]
    created_at: datetime
    updated_at: datetime


class TaskRunResponse(BaseModel):
    id: int
    task_id: int
    status: str
    started_at: datetime
    finished_at: Optional[datetime]
    duration_seconds: Optional[float]
    error_message: Optional[str]
    response_summary: Optional[str]


class TaskRunStatsResponse(BaseModel):
    total: int
    success: int
    failed: int
    other: int


class TaskListResponse(BaseModel):
    items: list[TaskResponse]
    total: int


# --- Routes ---

@router.get("", response_model=TaskListResponse)
async def list_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: Optional[str] = Query(None, alias="status"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """List current user's tasks."""
    query = select(Task).where(Task.user_id == current_user.id)

    if status_filter:
        query = query.where(Task.status == status_filter)

    query = query.order_by(col(Task.updated_at).desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await session.execute(query)
    tasks = result.scalars().all()

    # Get total
    count_query = select(Task).where(Task.user_id == current_user.id)
    if status_filter:
        count_query = count_query.where(Task.status == status_filter)
    total_result = await session.execute(count_query)
    total = len(total_result.scalars().all())

    return TaskListResponse(
        items=[
            TaskResponse(
                id=t.id,
                template_id=t.template_id,
                name=t.name,
                description=t.description,
                schedule_config=t.schedule_config,
                status=t.status,
                variables=t.variables,
                execution_config=t.execution_config or {},
                group_id=t.group_id,
                next_run_at=t.next_run_at,
                run_count=t.run_count,
                last_run_at=t.last_run_at,
                last_status=t.last_status,
                created_at=t.created_at,
                updated_at=t.updated_at,
            )
            for t in tasks
        ],
        total=total,
    )


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    request: TaskCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Create a new task."""
    _validate_task_config(request.schedule_config, request.execution_config)
    await _validate_task_relations(request.template_id, request.group_id, current_user, session)

    # Task quota check (0 = unlimited)
    from qd_server.api.admin import get_system_settings

    sys_settings = await get_system_settings(session)
    max_tasks = int(sys_settings.get("max_tasks_per_user", 0) or 0)
    if max_tasks > 0:
        from sqlmodel import func

        count = (
            await session.execute(
                select(func.count()).select_from(Task).where(Task.user_id == current_user.id)
            )
        ).scalar_one()
        if count >= max_tasks:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Task quota exceeded (max {max_tasks} per user)",
            )

    now = datetime.utcnow()
    task = Task(
        user_id=current_user.id,
        template_id=request.template_id,
        name=request.name,
        description=request.description,
        schedule_config=request.schedule_config,
        variables=request.variables,
        execution_config=request.execution_config,
        group_id=request.group_id,
        created_at=now,
        updated_at=now,
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)

    # Register with scheduler
    from qd_server.services.scheduler import scheduler
    scheduler.add_task(task)

    return TaskResponse(
        id=task.id,
        template_id=task.template_id,
        name=task.name,
        description=task.description,
        schedule_config=task.schedule_config,
        status=task.status,
        variables=task.variables,
        execution_config=task.execution_config or {},
        group_id=task.group_id,
        next_run_at=task.next_run_at,
        run_count=task.run_count,
        last_run_at=task.last_run_at,
        last_status=task.last_status,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Get a task by ID."""
    result = await session.execute(
        select(Task).where(Task.id == task_id, Task.user_id == current_user.id)
    )
    task = result.scalar_one_or_none()

    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    return TaskResponse(
        id=task.id,
        template_id=task.template_id,
        name=task.name,
        description=task.description,
        schedule_config=task.schedule_config,
        status=task.status,
        variables=task.variables,
        execution_config=task.execution_config or {},
        group_id=task.group_id,
        next_run_at=task.next_run_at,
        run_count=task.run_count,
        last_run_at=task.last_run_at,
        last_status=task.last_status,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


@router.put("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: int,
    request: TaskUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Update a task."""
    result = await session.execute(
        select(Task).where(Task.id == task_id, Task.user_id == current_user.id)
    )
    task = result.scalar_one_or_none()

    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    update_data = request.model_dump(exclude_unset=True)
    _validate_task_config(
        update_data.get("schedule_config", task.schedule_config),
        update_data.get("execution_config", task.execution_config),
    )
    if "group_id" in update_data:
        await _validate_group(update_data["group_id"], current_user, session)
    if "status" in update_data and update_data["status"] not in ("pending", "paused", "disabled"):
        raise HTTPException(status_code=422, detail="Invalid task status")
    for key, value in update_data.items():
        setattr(task, key, value)

    task.updated_at = datetime.utcnow()
    session.add(task)
    await session.commit()
    await session.refresh(task)

    from qd_server.services.scheduler import scheduler

    if task.status in ("paused", "disabled"):
        scheduler.remove_task(task.id)
    else:
        scheduler.add_task(task)

    return TaskResponse(
        id=task.id,
        template_id=task.template_id,
        name=task.name,
        description=task.description,
        schedule_config=task.schedule_config,
        status=task.status,
        variables=task.variables,
        execution_config=task.execution_config or {},
        group_id=task.group_id,
        next_run_at=task.next_run_at,
        run_count=task.run_count,
        last_run_at=task.last_run_at,
        last_status=task.last_status,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Delete a task."""
    result = await session.execute(
        select(Task).where(Task.id == task_id, Task.user_id == current_user.id)
    )
    task = result.scalar_one_or_none()

    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    from qd_server.models.notification import Notification

    await session.execute(sql_delete(TaskRun).where(TaskRun.task_id == task_id))
    await session.execute(sql_delete(Notification).where(Notification.task_id == task_id))
    await session.delete(task)
    await session.commit()

    # Remove from scheduler
    from qd_server.services.scheduler import scheduler
    scheduler.remove_task(task_id)


@router.post("/{task_id}/run", response_model=TaskRunResponse)
async def run_task(
    task_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Manually trigger a task run."""
    result = await session.execute(
        select(Task).where(Task.id == task_id, Task.user_id == current_user.id)
    )
    task = result.scalar_one_or_none()

    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    # Execute via scheduler (creates its own session) and return this exact run.
    from qd_server.services.scheduler import scheduler
    await session.commit()
    run = await scheduler.run_task_now(task_id)

    if run is None:
        raise HTTPException(
            status_code=409,
            detail="Task is not runnable (user, task, or template is disabled)",
        )

    return TaskRunResponse(
        id=run.id,
        task_id=run.task_id,
        status=run.status,
        started_at=run.started_at,
        finished_at=run.finished_at,
        duration_seconds=run.duration_seconds,
        error_message=run.error_message,
        response_summary=run.response_summary,
    )


@router.get("/{task_id}/runs", response_model=list[TaskRunResponse])
async def list_task_runs(
    task_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """List run history for a task."""
    # Verify task ownership
    task_result = await session.execute(
        select(Task).where(Task.id == task_id, Task.user_id == current_user.id)
    )
    if task_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Task not found")

    query = (
        select(TaskRun)
        .where(TaskRun.task_id == task_id, TaskRun.user_id == current_user.id)
        .order_by(col(TaskRun.started_at).desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await session.execute(query)
    runs = result.scalars().all()

    return [
        TaskRunResponse(
            id=r.id,
            task_id=r.task_id,
            status=r.status,
            started_at=r.started_at,
            finished_at=r.finished_at,
            duration_seconds=r.duration_seconds,
            error_message=r.error_message,
            response_summary=r.response_summary,
        )
        for r in runs
    ]


@router.get("/{task_id}/runs/stats", response_model=TaskRunStatsResponse)
async def get_task_run_stats(
    task_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Return run totals for one owned task."""
    await _get_owned_task(task_id, current_user, session)
    result = await session.execute(
        select(TaskRun.status, func.count())
        .where(
            TaskRun.task_id == task_id,
            TaskRun.user_id == current_user.id,
        )
        .group_by(TaskRun.status)
    )
    counts = {run_status: count for run_status, count in result.all()}
    total = sum(counts.values())
    success_count = counts.get("success", 0)
    failed_count = counts.get("failed", 0)
    return TaskRunStatsResponse(
        total=total,
        success=success_count,
        failed=failed_count,
        other=total - success_count - failed_count,
    )


@router.delete("/{task_id}/runs")
async def delete_task_runs(
    task_id: int,
    status: Optional[str] = Query(
        None, description="留空删除全部; 'success' 仅删成功; 'failed' 仅删失败 (QD v1 /task/N/log/del 对应)"
    ),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Delete run history for a task (all / success only / failed only)."""
    if status is not None and status not in ("success", "failed"):
        raise HTTPException(status_code=422, detail="status must be 'success' or 'failed'")

    await _get_owned_task(task_id, current_user, session)

    filters = [TaskRun.task_id == task_id, TaskRun.user_id == current_user.id]
    if status is not None:
        filters.append(TaskRun.status == status)
    count_result = await session.execute(
        select(func.count()).select_from(TaskRun).where(*filters)
    )
    deleted = count_result.scalar_one()
    await session.execute(sql_delete(TaskRun).where(*filters))
    await session.commit()
    return {"deleted": deleted, "task_id": task_id, "status": status or "all"}


# --- Cookie session management ---

class CookieItem(BaseModel):
    name: str
    value: str
    domain: Optional[str] = ""
    path: Optional[str] = "/"
    expires: Optional[int] = None
    secure: Optional[bool] = False


class CookieSessionResponse(BaseModel):
    task_id: int
    cookies: list[dict]
    count: int


async def _get_owned_task(task_id: int, current_user: User, session: AsyncSession) -> Task:
    result = await session.execute(
        select(Task).where(Task.id == task_id, Task.user_id == current_user.id)
    )
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


async def _validate_group(
    group_id: Optional[int], current_user: User, session: AsyncSession
) -> None:
    if group_id is None:
        return
    result = await session.execute(
        select(TaskGroup.id).where(
            TaskGroup.id == group_id,
            TaskGroup.user_id == current_user.id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Task group not found")


async def _validate_task_relations(
    template_id: int,
    group_id: Optional[int],
    current_user: User,
    session: AsyncSession,
) -> None:
    result = await session.execute(
        select(Template.id).where(
            Template.id == template_id,
            Template.user_id == current_user.id,
            Template.enabled == True,
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Template not found")
    await _validate_group(group_id, current_user, session)


def _validate_task_config(schedule_config: dict, execution_config: dict) -> None:
    if not isinstance(schedule_config, dict) or not isinstance(execution_config, dict):
        raise HTTPException(status_code=422, detail="Task configuration must be an object")

    schedule_type = schedule_config.get("schedule_type", "interval")
    if schedule_type == "interval":
        try:
            interval = int(schedule_config.get("interval_seconds", 3600))
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="Invalid interval_seconds") from exc
        if not 1 <= interval <= 365 * 24 * 3600:
            raise HTTPException(status_code=422, detail="interval_seconds is out of range")
    elif schedule_type == "cron":
        from apscheduler.triggers.cron import CronTrigger

        expression = str(schedule_config.get("cron_expression", ""))
        parts = expression.split()
        if len(parts) != 5:
            raise HTTPException(status_code=422, detail="cron_expression must have 5 fields")
        try:
            CronTrigger(
                minute=parts[0],
                hour=parts[1],
                day=parts[2],
                month=parts[3],
                day_of_week=parts[4],
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"Invalid cron_expression: {exc}") from exc
    elif schedule_type == "daily":
        run_time = schedule_config.get("run_time", "")
        if not any(
            _is_time_format(run_time, time_format)
            for time_format in ("%H:%M:%S", "%H:%M")
        ):
            raise HTTPException(status_code=422, detail="run_time must be HH:MM or HH:MM:SS")
    elif schedule_type == "once":
        run_at = schedule_config.get("run_at")
        if run_at:
            try:
                datetime.fromisoformat(str(run_at))
            except ValueError as exc:
                raise HTTPException(status_code=422, detail="Invalid run_at") from exc
    else:
        raise HTTPException(status_code=422, detail="Invalid schedule_type")

    bounds = {
        "retry_count": (0, 10),
        "retry_interval_seconds": (0, 86400),
        "random_delay_min": (0, 86400),
        "random_delay_max": (0, 86400),
    }
    values: dict[str, int] = {}
    for key, (minimum, maximum) in bounds.items():
        try:
            value = int(execution_config.get(key, 0) or 0)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=f"Invalid {key}") from exc
        if not minimum <= value <= maximum:
            raise HTTPException(status_code=422, detail=f"{key} is out of range")
        values[key] = value
    if values["random_delay_min"] > values["random_delay_max"]:
        raise HTTPException(status_code=422, detail="random delay minimum exceeds maximum")


def _is_time_format(value, time_format: str) -> bool:
    try:
        datetime.strptime(str(value), time_format)
        return True
    except (TypeError, ValueError):
        return False


@router.get("/{task_id}/cookies", response_model=CookieSessionResponse)
async def get_task_cookies(
    task_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """View the task's persistent cookie session."""
    task = await _get_owned_task(task_id, current_user, session)
    cookies = task.cookie_session or []
    return CookieSessionResponse(task_id=task_id, cookies=cookies, count=len(cookies))


@router.put("/{task_id}/cookies", response_model=CookieSessionResponse)
async def set_task_cookies(
    task_id: int,
    cookies: list[CookieItem],
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Replace the task's cookie session with the provided cookies."""
    from qd_core.client.cookie_session import CookieSession as CoreCookieSession

    task = await _get_owned_task(task_id, current_user, session)

    # Normalize through CookieSession to validate + canonical format
    cs = CoreCookieSession().from_json([c.model_dump() for c in cookies])
    task.cookie_session = cs.to_json()
    task.updated_at = datetime.utcnow()
    session.add(task)
    await session.commit()
    await session.refresh(task)

    return CookieSessionResponse(
        task_id=task_id, cookies=task.cookie_session, count=len(task.cookie_session)
    )


@router.delete("/{task_id}/cookies", response_model=CookieSessionResponse)
async def clear_task_cookies(
    task_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Clear the task's persistent cookie session."""
    task = await _get_owned_task(task_id, current_user, session)
    task.cookie_session = []
    task.updated_at = datetime.utcnow()
    session.add(task)
    await session.commit()

    return CookieSessionResponse(task_id=task_id, cookies=[], count=0)
