"""Template management API routes."""

from copy import deepcopy
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import or_
from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from qd_server.middleware.auth import get_current_user, get_session
from qd_server.models.task import Task, TaskRun
from qd_server.models.template import Template
from qd_server.models.user import User

router = APIRouter()


# --- Request/Response schemas ---

class TemplateCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    template_data: dict | list = {}
    variables: dict = {}
    tags: list[str] = []
    is_public: bool = False


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    template_data: Optional[dict | list] = None
    variables: Optional[dict] = None
    tags: Optional[list[str]] = None
    is_public: Optional[bool] = None
    enabled: Optional[bool] = None


class TemplateResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    template_data: dict | list
    variables: dict
    tags: list
    is_public: bool
    enabled: bool
    run_count: int
    created_at: datetime
    updated_at: datetime
    last_success_at: Optional[datetime] = None


class TemplateListResponse(BaseModel):
    items: list[TemplateResponse]
    total: int


class PublishedTemplateResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    author: Optional[str]
    version: str
    tags: list
    owner: str
    owned: bool
    installed: bool
    updated_at: datetime


class PublishedTemplateListResponse(BaseModel):
    items: list[PublishedTemplateResponse]
    total: int


async def _get_template_last_success(
    template_ids: list[int], user_id: int, session: AsyncSession
) -> dict[int, datetime | None]:
    """Return the latest successful run time for each owned template."""
    if not template_ids:
        return {}
    result = await session.execute(
        select(Task.template_id, func.max(func.coalesce(TaskRun.finished_at, TaskRun.started_at)))
        .join(TaskRun, TaskRun.task_id == Task.id)
        .where(
            Task.template_id.in_(template_ids),
            Task.user_id == user_id,
            TaskRun.user_id == user_id,
            TaskRun.status == "success",
        )
        .group_by(Task.template_id)
    )
    return {template_id: last_success_at for template_id, last_success_at in result.all()}


# --- Routes ---

@router.get("", response_model=TemplateListResponse)
async def list_templates(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """List current user's templates."""
    query = select(Template).where(Template.user_id == current_user.id)

    if search:
        query = query.where(col(Template.name).contains(search))

    query = query.order_by(col(Template.updated_at).desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await session.execute(query)
    templates = result.scalars().all()
    last_success = await _get_template_last_success(
        [template.id for template in templates], current_user.id, session
    )

    # Get total count
    count_query = select(Template).where(Template.user_id == current_user.id)
    if search:
        count_query = count_query.where(col(Template.name).contains(search))
    total_result = await session.execute(count_query)
    total = len(total_result.scalars().all())

    return TemplateListResponse(
        items=[
            TemplateResponse(
                id=t.id,
                name=t.name,
                description=t.description,
                template_data=t.template_data,
                variables=t.variables,
                tags=t.tags,
                is_public=t.is_public,
                enabled=t.enabled,
                run_count=t.run_count,
                created_at=t.created_at,
                updated_at=t.updated_at,
                last_success_at=last_success.get(t.id),
            )
            for t in templates
        ],
        total=total,
    )


@router.get("/published", response_model=PublishedTemplateListResponse)
async def list_published_templates(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """List enabled templates explicitly published by all users."""
    filters = [Template.is_public, Template.enabled, User.is_active]
    if search and search.strip():
        term = search.strip()
        filters.append(
            or_(
                col(Template.name).contains(term),
                col(Template.description).contains(term),
                col(Template.author).contains(term),
                col(User.username).contains(term),
            )
        )

    result = await session.execute(
        select(Template, User.username)
        .join(User, User.id == Template.user_id)
        .where(*filters)
        .order_by(col(Template.updated_at).desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = result.all()
    total = (
        await session.execute(
            select(func.count())
            .select_from(Template)
            .join(User, User.id == Template.user_id)
            .where(*filters)
        )
    ).scalar_one()

    owned_tags = (
        await session.execute(select(Template.tags).where(Template.user_id == current_user.id))
    ).scalars().all()
    installed_source_ids = {
        int(tag.removeprefix("published-source:"))
        for tags in owned_tags
        for tag in (tags or [])
        if isinstance(tag, str)
        and tag.startswith("published-source:")
        and tag.removeprefix("published-source:").isdigit()
    }

    return PublishedTemplateListResponse(
        items=[
            PublishedTemplateResponse(
                id=template.id,
                name=template.name,
                description=template.description,
                author=template.author,
                version=template.version,
                tags=template.tags,
                owner=owner,
                owned=template.user_id == current_user.id,
                installed=(
                    template.user_id == current_user.id
                    or template.id in installed_source_ids
                ),
                updated_at=template.updated_at,
            )
            for template, owner in rows
        ],
        total=total,
    )


@router.post(
    "/published/{template_id}/install",
    response_model=TemplateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def install_published_template(
    template_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Install a private copy of another user's published template."""
    result = await session.execute(
        select(Template)
        .join(User, User.id == Template.user_id)
        .where(
            Template.id == template_id,
            Template.is_public,
            Template.enabled,
            User.is_active,
        )
    )
    source = result.scalar_one_or_none()
    if source is None:
        raise HTTPException(status_code=404, detail="Published template not found")
    if source.user_id == current_user.id:
        raise HTTPException(status_code=409, detail="This template already belongs to you")

    marker = f"published-source:{source.id}"
    existing_tags = (
        await session.execute(select(Template.tags).where(Template.user_id == current_user.id))
    ).scalars().all()
    if any(marker in (tags or []) for tags in existing_tags):
        raise HTTPException(status_code=409, detail="Published template already installed")

    now = datetime.utcnow()
    template = Template(
        user_id=current_user.id,
        name=source.name,
        description=source.description,
        author=source.author,
        version=source.version,
        template_data=deepcopy(source.template_data),
        variables=deepcopy(source.variables),
        tags=[
            *[
                tag
                for tag in (source.tags or [])
                if not str(tag).startswith("published-source:")
            ],
            marker,
        ],
        enabled=True,
        is_public=False,
        created_at=now,
        updated_at=now,
    )
    session.add(template)
    await session.commit()
    await session.refresh(template)

    return TemplateResponse(
        id=template.id,
        name=template.name,
        description=template.description,
        template_data=template.template_data,
        variables=template.variables,
        tags=template.tags,
        is_public=template.is_public,
        enabled=template.enabled,
        run_count=template.run_count,
        created_at=template.created_at,
        updated_at=template.updated_at,
        last_success_at=None,
    )


@router.post("", response_model=TemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_template(
    request: TemplateCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Create a new template."""
    now = datetime.utcnow()
    template = Template(
        user_id=current_user.id,
        name=request.name,
        description=request.description,
        template_data=request.template_data,
        variables=request.variables,
        tags=request.tags,
        is_public=request.is_public,
        created_at=now,
        updated_at=now,
    )
    session.add(template)
    await session.commit()
    await session.refresh(template)

    return TemplateResponse(
        id=template.id,
        name=template.name,
        description=template.description,
        template_data=template.template_data,
        variables=template.variables,
        tags=template.tags,
        is_public=template.is_public,
        enabled=template.enabled,
        run_count=template.run_count,
        created_at=template.created_at,
        updated_at=template.updated_at,
        last_success_at=None,
    )


@router.get("/{template_id}", response_model=TemplateResponse)
async def get_template(
    template_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Get a template by ID."""
    result = await session.execute(
        select(Template).where(
            Template.id == template_id,
            Template.user_id == current_user.id,
        )
    )
    template = result.scalar_one_or_none()

    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")

    last_success_at = (await _get_template_last_success([template.id], current_user.id, session)).get(template.id)
    return TemplateResponse(
        id=template.id,
        name=template.name,
        description=template.description,
        template_data=template.template_data,
        variables=template.variables,
        tags=template.tags,
        is_public=template.is_public,
        enabled=template.enabled,
        run_count=template.run_count,
        created_at=template.created_at,
        updated_at=template.updated_at,
        last_success_at=last_success_at,
    )


@router.put("/{template_id}", response_model=TemplateResponse)
async def update_template(
    template_id: int,
    request: TemplateUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Update a template."""
    result = await session.execute(
        select(Template).where(
            Template.id == template_id,
            Template.user_id == current_user.id,
        )
    )
    template = result.scalar_one_or_none()

    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")

    update_data = request.model_dump(exclude_unset=True)
    enabled_changed = "enabled" in update_data and update_data["enabled"] != template.enabled
    for key, value in update_data.items():
        setattr(template, key, value)

    template.updated_at = datetime.utcnow()
    session.add(template)
    await session.commit()
    await session.refresh(template)

    if enabled_changed:
        from qd_server.services.scheduler import scheduler

        tasks_result = await session.execute(
            select(Task).where(
                Task.template_id == template.id,
                Task.user_id == current_user.id,
            )
        )
        for task in tasks_result.scalars().all():
            if template.enabled and task.status not in ("paused", "disabled"):
                scheduler.add_task(task)
            else:
                scheduler.remove_task(task.id)

    return TemplateResponse(
        id=template.id,
        name=template.name,
        description=template.description,
        template_data=template.template_data,
        variables=template.variables,
        tags=template.tags,
        is_public=template.is_public,
        enabled=template.enabled,
        run_count=template.run_count,
        created_at=template.created_at,
        updated_at=template.updated_at,
        last_success_at=(await _get_template_last_success([template.id], current_user.id, session)).get(template.id),
    )


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Delete a template."""
    result = await session.execute(
        select(Template).where(
            Template.id == template_id,
            Template.user_id == current_user.id,
        )
    )
    template = result.scalar_one_or_none()

    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")

    task_result = await session.execute(select(Task.id).where(Task.template_id == template_id).limit(1))
    if task_result.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Template is used by a task")

    await session.delete(template)
    await session.commit()


@router.get("/{template_id}/export")
async def export_template(
    template_id: int,
    format: str = Query("qd2", description="Export format: qd2 or har"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Export a template as QD2 JSON or HAR format."""
    result = await session.execute(
        select(Template).where(
            Template.id == template_id,
            Template.user_id == current_user.id,
        )
    )
    template = result.scalar_one_or_none()

    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")

    # template_data can be a dict (QD2 native) or list (QD v1 tpl format)
    tpl_data = template.template_data
    if isinstance(tpl_data, list):
        tpl_requests = [e.get("request", {}) for e in tpl_data if isinstance(e, dict)]
    else:
        tpl_requests = tpl_data.get("requests", [])

    if format == "har":
        # Convert to HAR 1.2 format
        har_data = {
            "log": {
                "version": "1.2",
                "creator": {"name": "QD2", "version": "25.1.0"},
                "entries": [],
            }
        }
        requests = tpl_requests
        for req in requests:
            har_entry = {
                "request": {
                    "method": req.get("method", "GET"),
                    "url": req.get("url", ""),
                    "httpVersion": "HTTP/1.1",
                    "headers": [
                        {"name": h["name"], "value": h["value"]}
                        for h in req.get("headers", [])
                    ],
                    "queryString": [],
                    "cookies": [],
                },
                "response": {
                    "status": 200,
                    "statusText": "OK",
                    "httpVersion": "HTTP/1.1",
                    "headers": [],
                    "cookies": [],
                    "content": {"size": 0, "mimeType": "text/plain"},
                },
            }
            har_data["log"]["entries"].append(har_entry)

        from fastapi.responses import JSONResponse
        return JSONResponse(
            content=har_data,
            headers={
                "Content-Disposition": f'attachment; filename="{template.name}.har"'
            },
        )

    # QD2 format (default)
    from fastapi.responses import JSONResponse
    export_data = {
        "name": template.name,
        "description": template.description,
        "version": "1.0",
        "tags": template.tags,
        "variables": template.variables,
        "requests": tpl_requests,
    }
    return JSONResponse(
        content=export_data,
        headers={
            "Content-Disposition": f'attachment; filename="{template.name}.json"'
        },
    )


@router.post("/import")
async def import_template(
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Import a template from QD2 JSON or HAR format."""
    body = await request.json()
    metadata = body if isinstance(body, dict) else {}

    # Detect format
    if isinstance(body, list):
        template_data = body
        name = "Imported"
    elif "log" in body and "entries" in body.get("log", {}):
        # HAR format
        entries = body["log"]["entries"]
        requests = []
        for entry in entries:
            req = dict(entry.get("request", {}))
            req["checked"] = entry.get("checked", req.get("checked", True))
            comment = entry.get("comment") or req.get("comment")
            if comment:
                req["_comment"] = comment
            rule = entry.get("rule", {})
            success_asserts = entry.get("success_asserts", rule.get("success_asserts", []))
            failed_asserts = entry.get("failed_asserts", rule.get("failed_asserts", []))
            extract_variables = entry.get("extract_variables", rule.get("extract_variables", []))
            if success_asserts or failed_asserts or extract_variables:
                req["rule"] = {
                    "success_asserts": success_asserts,
                    "failed_asserts": failed_asserts,
                    "extract_variables": extract_variables,
                }
            requests.append(req)

        template_data = {"name": "Imported HAR", "requests": requests}
        name = body.get("log", {}).get("creator", {}).get("comment", "Imported HAR")
    else:
        # QD2 format
        template_data = {
            "name": body.get("name", "Imported"),
            "requests": body.get("requests", []),
        }
        name = body.get("name", "Imported")

    now = datetime.utcnow()
    template = Template(
        user_id=current_user.id,
        name=name,
        description=metadata.get("description", ""),
        template_data=template_data,
        variables=metadata.get("variables", {}),
        tags=metadata.get("tags", []),
        created_at=now,
        updated_at=now,
    )
    session.add(template)
    await session.commit()
    await session.refresh(template)

    return TemplateResponse(
        id=template.id,
        name=template.name,
        description=template.description,
        template_data=template.template_data,
        variables=template.variables,
        tags=template.tags,
        is_public=template.is_public,
        enabled=template.enabled,
        run_count=template.run_count,
        created_at=template.created_at,
        updated_at=template.updated_at,
        last_success_at=None,
    )
