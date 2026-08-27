"""Published template browsing and installation tests."""

import pytest
import qd_server.models  # noqa: F401 - register all tables
from fastapi import HTTPException
from qd_server.api.templates import install_published_template, list_published_templates
from qd_server.models.template import Template
from qd_server.models.user import User
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, select
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
async def test_published_templates_can_be_searched_and_installed(session):
    publisher = User(username="publisher", hashed_password="x")
    consumer = User(username="consumer", hashed_password="x")
    session.add_all([publisher, consumer])
    await session.flush()
    public = Template(
        user_id=publisher.id,
        name="Visible template",
        description="published description",
        author="legacy author",
        template_data={"requests": [{"method": "GET", "url": "https://example.test"}]},
        variables={"token": "default"},
        tags=["group:Demo"],
        is_public=True,
    )
    private = Template(user_id=publisher.id, name="Private template", is_public=False)
    session.add_all([public, private])
    await session.commit()

    page = await list_published_templates(1, 20, "Visible", consumer, session)
    assert page.total == 1
    assert page.items[0].owner == "publisher"
    assert page.items[0].installed is False

    installed = await install_published_template(public.id, consumer, session)
    assert installed.name == public.name
    assert installed.is_public is False
    assert installed.template_data == public.template_data
    assert installed.variables == public.variables
    assert f"published-source:{public.id}" in installed.tags

    clones = (
        await session.execute(select(Template).where(Template.user_id == consumer.id))
    ).scalars().all()
    assert len(clones) == 1

    refreshed_page = await list_published_templates(1, 20, None, consumer, session)
    assert refreshed_page.items[0].installed is True

    with pytest.raises(HTTPException) as duplicate_error:
        await install_published_template(public.id, consumer, session)
    assert duplicate_error.value.status_code == 409
