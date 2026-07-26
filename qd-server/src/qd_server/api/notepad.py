"""Notepad API routes."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from qd_server.middleware.auth import get_current_user, get_session
from qd_server.models.notepad import Notepad
from qd_server.models.user import User

router = APIRouter()


class NotepadCreate(BaseModel):
    title: str
    content: str = ""
    category: Optional[str] = None
    tags: Optional[str] = None


class NotepadUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[str] = None
    sort_order: Optional[int] = None


class NotepadResponse(BaseModel):
    id: int
    title: str
    content: str
    category: Optional[str]
    tags: Optional[str]
    sort_order: int
    created_at: datetime
    updated_at: datetime


@router.get("", response_model=list[NotepadResponse])
async def list_notepads(
    category: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """List current user's notepad entries."""
    query = select(Notepad).where(Notepad.user_id == current_user.id)

    if category:
        query = query.where(Notepad.category == category)

    query = query.order_by(col(Notepad.sort_order).asc(), col(Notepad.updated_at).desc())

    result = await session.execute(query)
    notepads = result.scalars().all()

    return [
        NotepadResponse(
            id=n.id,
            title=n.title,
            content=n.content,
            category=n.category,
            tags=n.tags,
            sort_order=n.sort_order,
            created_at=n.created_at,
            updated_at=n.updated_at,
        )
        for n in notepads
    ]


@router.post("", response_model=NotepadResponse, status_code=status.HTTP_201_CREATED)
async def create_notepad(
    request: NotepadCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Create a new notepad entry."""
    now = datetime.utcnow()
    notepad = Notepad(
        user_id=current_user.id,
        title=request.title,
        content=request.content,
        category=request.category,
        tags=request.tags,
        created_at=now,
        updated_at=now,
    )
    session.add(notepad)
    await session.commit()
    await session.refresh(notepad)

    return NotepadResponse(
        id=notepad.id,
        title=notepad.title,
        content=notepad.content,
        category=notepad.category,
        tags=notepad.tags,
        sort_order=notepad.sort_order,
        created_at=notepad.created_at,
        updated_at=notepad.updated_at,
    )


@router.get("/{notepad_id}", response_model=NotepadResponse)
async def get_notepad(
    notepad_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Get a notepad entry by ID."""
    result = await session.execute(
        select(Notepad).where(Notepad.id == notepad_id, Notepad.user_id == current_user.id)
    )
    notepad = result.scalar_one_or_none()

    if notepad is None:
        raise HTTPException(status_code=404, detail="Notepad entry not found")

    return NotepadResponse(
        id=notepad.id,
        title=notepad.title,
        content=notepad.content,
        category=notepad.category,
        tags=notepad.tags,
        sort_order=notepad.sort_order,
        created_at=notepad.created_at,
        updated_at=notepad.updated_at,
    )


@router.put("/{notepad_id}", response_model=NotepadResponse)
async def update_notepad(
    notepad_id: int,
    request: NotepadUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Update a notepad entry."""
    result = await session.execute(
        select(Notepad).where(Notepad.id == notepad_id, Notepad.user_id == current_user.id)
    )
    notepad = result.scalar_one_or_none()

    if notepad is None:
        raise HTTPException(status_code=404, detail="Notepad entry not found")

    update_data = request.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(notepad, key, value)

    notepad.updated_at = datetime.utcnow()
    session.add(notepad)
    await session.commit()
    await session.refresh(notepad)

    return NotepadResponse(
        id=notepad.id,
        title=notepad.title,
        content=notepad.content,
        category=notepad.category,
        tags=notepad.tags,
        sort_order=notepad.sort_order,
        created_at=notepad.created_at,
        updated_at=notepad.updated_at,
    )


@router.delete("/{notepad_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_notepad(
    notepad_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Delete a notepad entry."""
    result = await session.execute(
        select(Notepad).where(Notepad.id == notepad_id, Notepad.user_id == current_user.id)
    )
    notepad = result.scalar_one_or_none()

    if notepad is None:
        raise HTTPException(status_code=404, detail="Notepad entry not found")

    await session.delete(notepad)
    await session.commit()
