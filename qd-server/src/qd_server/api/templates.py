"""Template management API routes."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from qd_server.middleware.auth import get_current_user, get_session
from qd_server.models.template import Template
from qd_server.models.user import User

router = APIRouter()


# --- Request/Response schemas ---

class TemplateCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    template_data: dict = {}
    variables: dict = {}
    tags: list[str] = []
    is_public: bool = False


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    template_data: Optional[dict] = None
    variables: Optional[dict] = None
    tags: Optional[list[str]] = None
    is_public: Optional[bool] = None
    enabled: Optional[bool] = None


class TemplateResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    template_data: dict
    variables: dict
    tags: list
    is_public: bool
    enabled: bool
    run_count: int
    created_at: datetime
    updated_at: datetime


class TemplateListResponse(BaseModel):
    items: list[TemplateResponse]
    total: int


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
            )
            for t in templates
        ],
        total=total,
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
    for key, value in update_data.items():
        setattr(template, key, value)

    template.updated_at = datetime.utcnow()
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

    if format == "har":
        # Convert to HAR 1.2 format
        har_data = {
            "log": {
                "version": "1.2",
                "creator": {"name": "QD2", "version": "25.1.0"},
                "entries": [],
            }
        }
        requests = template.template_data.get("requests", [])
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
        "requests": template.template_data.get("requests", []),
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
    from fastapi import Request as FastAPIRequest
    body = await request.json()

    # Detect format
    if "log" in body and "entries" in body.get("log", {}):
        # HAR format
        entries = body["log"]["entries"]
        requests = []
        for entry in entries:
            har_req = entry.get("request", {})
            req = {
                "method": har_req.get("method", "GET"),
                "url": har_req.get("url", ""),
                "headers": [
                    {"name": h["name"], "value": h["value"]}
                    for h in har_req.get("headers", [])
                ],
            }
            post_data = har_req.get("postData")
            if post_data:
                req["postData"] = {
                    "mimeType": post_data.get("mimeType", "text/plain"),
                    "text": post_data.get("text", ""),
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
        description=body.get("description", ""),
        template_data=template_data,
        variables=body.get("variables", {}),
        tags=body.get("tags", []),
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
    )
