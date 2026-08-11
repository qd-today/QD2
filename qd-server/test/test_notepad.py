"""Multiple notepad entries and ownership isolation regression tests."""

import pytest
import qd_server.models  # noqa: F401 - register all tables
from fastapi import HTTPException
from qd_server.api.notepad import (
    NotepadCreate,
    NotepadUpdate,
    create_notepad,
    delete_notepad,
    get_notepad,
    list_notepads,
    update_notepad,
)
from qd_server.models.user import User
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db_session:
        yield db_session
    await engine.dispose()


@pytest.mark.asyncio
async def test_notepads_have_independent_ids_and_are_scoped_to_owner(session: AsyncSession) -> None:
    owner = User(username="notepad-owner", hashed_password="x")
    other = User(username="notepad-other", hashed_password="x")
    session.add(owner)
    session.add(other)
    await session.commit()
    await session.refresh(owner)
    await session.refresh(other)

    alpha = await create_notepad(NotepadCreate(title="Alpha", content="alpha content"), owner, session)
    beta = await create_notepad(NotepadCreate(title="Beta", content="beta content"), owner, session)
    foreign = await create_notepad(NotepadCreate(title="Foreign"), other, session)

    assert alpha.id != beta.id
    assert {note.id for note in await list_notepads(None, owner, session)} == {alpha.id, beta.id}

    updated = await update_notepad(
        beta.id,
        NotepadUpdate(title="Beta updated", content="new beta content"),
        owner,
        session,
    )
    assert updated.title == "Beta updated"
    assert (await get_notepad(beta.id, owner, session)).content == "new beta content"

    with pytest.raises(HTTPException) as foreign_error:
        await get_notepad(foreign.id, owner, session)
    assert foreign_error.value.status_code == 404

    await delete_notepad(alpha.id, owner, session)
    remaining = await list_notepads(None, owner, session)
    assert [note.id for note in remaining] == [beta.id]
