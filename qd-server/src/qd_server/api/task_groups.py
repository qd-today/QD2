"""Task group management API routes."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from qd_server.middleware.auth import get_current_user, get_session
from qd_server.models.task_group import TaskGroup
from qd_server.models.user import User

router = APIRouter()


class TaskGroupCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    color: Optional[str] = None


class TaskGroupUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    color: Optional[str] = None
    sort_order: Optional[int] = None


class TaskGroupResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    color: Optional[str]
    sort_order: int
    task_count: int = 0
    created_at: datetime
    updated_at: datetime


@router.get("", response_model=list[TaskGroupResponse])
async def list_groups(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """List all task groups for current user."""
    result = await session.execute(
        select(TaskGroup)
        .where(TaskGroup.user_id == current_user.id)
        .order_by(col(TaskGroup.sort_order).asc(), col(TaskGroup.created_at).desc())
    )
    groups = result.scalars().all()

    # Get task counts per group
    from qd_server.models.task import Task
    result = await session.execute(select(Task).where(Task.user_id == current_user.id))
    all_tasks = result.scalars().all()
    count_map = {}
    for t in all_tasks:
        gid = t.group_id or 0
        count_map[gid] = count_map.get(gid, 0) + 1

    return [
        TaskGroupResponse(
            id=g.id,
            name=g.name,
            description=g.description,
            color=g.color,
            sort_order=g.sort_order,
            task_count=count_map.get(g.id, 0),
            created_at=g.created_at,
            updated_at=g.updated_at,
        )
        for g in groups
    ]


@router.post("", response_model=TaskGroupResponse, status_code=status.HTTP_201_CREATED)
async def create_group(
    request: TaskGroupCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Create a new task group."""
    now = datetime.utcnow()
    group = TaskGroup(
        user_id=current_user.id,
        name=request.name,
        description=request.description,
        color=request.color,
        created_at=now,
        updated_at=now,
    )
    session.add(group)
    await session.commit()
    await session.refresh(group)

    return TaskGroupResponse(
        id=group.id,
        name=group.name,
        description=group.description,
        color=group.color,
        sort_order=group.sort_order,
        task_count=0,
        created_at=group.created_at,
        updated_at=group.updated_at,
    )


@router.put("/{group_id}", response_model=TaskGroupResponse)
async def update_group(
    group_id: int,
    request: TaskGroupUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Update a task group."""
    result = await session.execute(
        select(TaskGroup).where(TaskGroup.id == group_id, TaskGroup.user_id == current_user.id)
    )
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    update_data = request.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(group, key, value)
    group.updated_at = datetime.utcnow()

    session.add(group)
    await session.commit()
    await session.refresh(group)

    return TaskGroupResponse(
        id=group.id,
        name=group.name,
        description=group.description,
        color=group.color,
        sort_order=group.sort_order,
        task_count=0,
        created_at=group.created_at,
        updated_at=group.updated_at,
    )


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(
    group_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Delete a task group. Tasks in the group will be ungrouped."""
    result = await session.execute(
        select(TaskGroup).where(TaskGroup.id == group_id, TaskGroup.user_id == current_user.id)
    )
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    # Ungroup tasks in this group
    from qd_server.models.task import Task
    tasks_result = await session.execute(
        select(Task).where(Task.group_id == group_id, Task.user_id == current_user.id)
    )
    for task in tasks_result.scalars().all():
        task.group_id = None
        session.add(task)

    await session.delete(group)
    await session.commit()
