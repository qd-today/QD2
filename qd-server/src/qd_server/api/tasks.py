"""Task management API routes."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from qd_server.middleware.auth import get_current_user, get_session
from qd_server.models.task import Task, TaskRun
from qd_server.models.user import User

router = APIRouter()


# --- Request/Response schemas ---

class TaskCreate(BaseModel):
    template_id: int
    name: str
    description: Optional[str] = ""
    schedule_config: dict = {}
    variables: dict = {}
    group_id: Optional[int] = None


class TaskUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    schedule_config: Optional[dict] = None
    variables: Optional[dict] = None
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
    now = datetime.utcnow()
    task = Task(
        user_id=current_user.id,
        template_id=request.template_id,
        name=request.name,
        description=request.description,
        schedule_config=request.schedule_config,
        variables=request.variables,
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
    for key, value in update_data.items():
        setattr(task, key, value)

    task.updated_at = datetime.utcnow()
    session.add(task)
    await session.commit()
    await session.refresh(task)

    return TaskResponse(
        id=task.id,
        template_id=task.template_id,
        name=task.name,
        description=task.description,
        schedule_config=task.schedule_config,
        status=task.status,
        variables=task.variables,
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

    # Execute via scheduler (creates its own session)
    from qd_server.services.scheduler import scheduler
    await scheduler.run_task_now(task_id)

    # Get the latest run record (scheduler creates it)
    from sqlalchemy import desc
    runs_result = await session.execute(
        select(TaskRun)
        .where(TaskRun.task_id == task_id)
        .order_by(desc(TaskRun.started_at))
        .limit(1)
    )
    run = runs_result.scalar_one_or_none()

    if run is None:
        # Fallback: should not happen, but handle gracefully
        run = TaskRun(
            task_id=task.id,
            user_id=current_user.id,
            status="unknown",
            started_at=datetime.utcnow(),
            finished_at=datetime.utcnow(),
            duration_seconds=0.0,
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
        .where(TaskRun.task_id == task_id)
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
