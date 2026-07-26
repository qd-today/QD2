"""Notification management API routes."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from qd_server.middleware.auth import get_current_user, get_session
from qd_server.models.notification import Notification
from qd_server.models.user import User

router = APIRouter()


class NotificationCreate(BaseModel):
    name: str
    notification_type: str  # webhook, email
    config: dict = {}
    task_id: Optional[int] = None
    on_success: bool = True
    on_failure: bool = True


class NotificationUpdate(BaseModel):
    name: Optional[str] = None
    config: Optional[dict] = None
    enabled: Optional[bool] = None
    on_success: Optional[bool] = None
    on_failure: Optional[bool] = None


class NotificationResponse(BaseModel):
    id: int
    name: str
    notification_type: str
    enabled: bool
    config: dict
    task_id: Optional[int]
    on_success: bool
    on_failure: bool
    created_at: datetime


@router.get("", response_model=list[NotificationResponse])
async def list_notifications(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """List current user's notifications."""
    result = await session.execute(
        select(Notification)
        .where(Notification.user_id == current_user.id)
        .order_by(col(Notification.created_at).desc())
    )
    notifications = result.scalars().all()

    return [
        NotificationResponse(
            id=n.id,
            name=n.name,
            notification_type=n.notification_type,
            enabled=n.enabled,
            config=n.config,
            task_id=n.task_id,
            on_success=n.on_success,
            on_failure=n.on_failure,
            created_at=n.created_at,
        )
        for n in notifications
    ]


@router.post("", response_model=NotificationResponse, status_code=status.HTTP_201_CREATED)
async def create_notification(
    request: NotificationCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Create a new notification."""
    notification = Notification(
        user_id=current_user.id,
        name=request.name,
        notification_type=request.notification_type,
        config=request.config,
        task_id=request.task_id,
        on_success=request.on_success,
        on_failure=request.on_failure,
    )
    session.add(notification)
    await session.commit()
    await session.refresh(notification)

    return NotificationResponse(
        id=notification.id,
        name=notification.name,
        notification_type=notification.notification_type,
        enabled=notification.enabled,
        config=notification.config,
        task_id=notification.task_id,
        on_success=notification.on_success,
        on_failure=notification.on_failure,
        created_at=notification.created_at,
    )


@router.put("/{notification_id}", response_model=NotificationResponse)
async def update_notification(
    notification_id: int,
    request: NotificationUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Update a notification."""
    result = await session.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == current_user.id,
        )
    )
    notification = result.scalar_one_or_none()

    if notification is None:
        raise HTTPException(status_code=404, detail="Notification not found")

    update_data = request.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(notification, key, value)

    session.add(notification)
    await session.commit()
    await session.refresh(notification)

    return NotificationResponse(
        id=notification.id,
        name=notification.name,
        notification_type=notification.notification_type,
        enabled=notification.enabled,
        config=notification.config,
        task_id=notification.task_id,
        on_success=notification.on_success,
        on_failure=notification.on_failure,
        created_at=notification.created_at,
    )


@router.delete("/{notification_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_notification(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Delete a notification."""
    result = await session.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == current_user.id,
        )
    )
    notification = result.scalar_one_or_none()

    if notification is None:
        raise HTTPException(status_code=404, detail="Notification not found")

    await session.delete(notification)
    await session.commit()
