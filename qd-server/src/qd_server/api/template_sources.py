"""Template subscription API — subscribe to public template repositories.

Manifest format (qd-today/templates tpls_history.json):
{
  "version": "20230315",
  "har": {
    "模板名": {
      "name": "...", "author": "...", "comments": "...", "filename": "...",
      "url": "https://raw.githubusercontent.com/...", "update": true,
      "content": "<base64 of QD v1 tpl JSON>"
    }, ...
  }
}
"""

import base64
import json
from datetime import datetime
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from qd_server.middleware.auth import get_current_user, get_session
from qd_server.models.template import Template
from qd_server.models.template_source import DEFAULT_REPO_URL, TemplateSource
from qd_server.models.user import User

router = APIRouter()


# --- Schemas ---

class SourceCreate(BaseModel):
    name: str
    url: str = DEFAULT_REPO_URL


class SourceResponse(BaseModel):
    id: int
    name: str
    url: str
    enabled: bool
    last_sync_at: Optional[datetime]
    manifest_version: Optional[str]
    template_count: int


class PublicTemplateItem(BaseModel):
    name: str
    author: str = ""
    comments: str = ""
    filename: str = ""
    installed: bool = False


class PublicTemplateList(BaseModel):
    source_id: int
    version: Optional[str]
    total: int
    items: list[PublicTemplateItem]


# --- helpers ---

async def _get_owned_source(source_id: int, user: User, session: AsyncSession) -> TemplateSource:
    result = await session.execute(
        select(TemplateSource).where(TemplateSource.id == source_id, TemplateSource.user_id == user.id)
    )
    source = result.scalar_one_or_none()
    if source is None:
        raise HTTPException(status_code=404, detail="Template source not found")
    return source


def _source_response(s: TemplateSource) -> SourceResponse:
    return SourceResponse(
        id=s.id,
        name=s.name,
        url=s.url,
        enabled=s.enabled,
        last_sync_at=s.last_sync_at,
        manifest_version=s.manifest_version,
        template_count=s.template_count,
    )


async def _fetch_manifest(url: str) -> dict:
    """Download and parse a tpls_history.json manifest."""
    try:
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch manifest: {e}") from e
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=502, detail=f"Manifest is not valid JSON: {e}") from e

    if not isinstance(data, dict) or "har" not in data:
        raise HTTPException(status_code=502, detail="Manifest missing 'har' key (not a tpls_history.json?)")
    return data


# --- Routes ---

@router.get("", response_model=list[SourceResponse])
async def list_sources(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """List subscribed template sources."""
    result = await session.execute(
        select(TemplateSource).where(TemplateSource.user_id == current_user.id).order_by(col(TemplateSource.id))
    )
    return [_source_response(s) for s in result.scalars().all()]


@router.post("", response_model=SourceResponse, status_code=status.HTTP_201_CREATED)
async def create_source(
    request: SourceCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Subscribe to a template repository."""
    now = datetime.utcnow()
    source = TemplateSource(
        user_id=current_user.id,
        name=request.name,
        url=request.url,
        created_at=now,
        updated_at=now,
    )
    session.add(source)
    await session.commit()
    await session.refresh(source)
    return _source_response(source)


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source(
    source_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Unsubscribe from a template repository."""
    source = await _get_owned_source(source_id, current_user, session)
    await session.delete(source)
    await session.commit()


@router.post("/{source_id}/sync", response_model=SourceResponse)
async def sync_source(
    source_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Fetch the latest manifest from the repository."""
    source = await _get_owned_source(source_id, current_user, session)

    data = await _fetch_manifest(source.url)
    har = data.get("har") or {}

    source.manifest = har
    source.manifest_version = str(data.get("version") or "")
    source.template_count = len(har)
    source.last_sync_at = datetime.utcnow()
    source.updated_at = datetime.utcnow()
    session.add(source)
    await session.commit()
    await session.refresh(source)
    return _source_response(source)


@router.get("/{source_id}/templates", response_model=PublicTemplateList)
async def list_public_templates(
    source_id: int,
    search: Optional[str] = Query(None, description="Filter by name/author/comments"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Browse templates available in a synced repository."""
    source = await _get_owned_source(source_id, current_user, session)
    manifest = source.manifest or {}

    # names of already-installed templates for this user
    result = await session.execute(select(Template.name).where(Template.user_id == current_user.id))
    installed_names = {row[0] for row in result.all()}

    items = []
    for name, meta in manifest.items():
        if not isinstance(meta, dict):
            continue
        if search:
            haystack = f"{name} {meta.get('author', '')} {meta.get('comments', '')}".lower()
            if search.lower() not in haystack:
                continue
        items.append(
            PublicTemplateItem(
                name=name,
                author=meta.get("author", "") or "",
                comments=meta.get("comments", "") or "",
                filename=meta.get("filename", "") or "",
                installed=name in installed_names,
            )
        )

    items.sort(key=lambda x: x.name)
    total = len(items)
    start = (page - 1) * page_size
    items = items[start : start + page_size]

    return PublicTemplateList(
        source_id=source_id,
        version=source.manifest_version,
        total=total,
        items=items,
    )


@router.post("/{source_id}/install/{template_name}", status_code=status.HTTP_201_CREATED)
async def install_template(
    source_id: int,
    template_name: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Install a public template into the user's template library."""
    source = await _get_owned_source(source_id, current_user, session)
    manifest = source.manifest or {}

    meta = manifest.get(template_name)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"Template '{template_name}' not in source manifest")

    # Decode template content: base64 of QD v1 tpl JSON
    content_b64 = meta.get("content") or ""
    tpl_data = None
    if content_b64:
        try:
            tpl_data = json.loads(base64.b64decode(content_b64).decode("utf-8"))
        except Exception:
            tpl_data = None

    if tpl_data is None:
        # Fallback: fetch the .har file from its URL
        url = meta.get("url")
        if not url:
            raise HTTPException(status_code=502, detail="Template has no content and no URL")
        try:
            async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                tpl_data = resp.json()
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Failed to download template: {e}") from e

    # Validate it parses (QD v1 list format or HAR)
    from qd_core.client.har import HARParser

    try:
        parsed = HARParser.parse_dict(tpl_data, source_file=meta.get("filename") or template_name)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Template failed to parse: {e}") from e

    now = datetime.utcnow()
    template = Template(
        user_id=current_user.id,
        name=template_name,
        description=(meta.get("comments") or "").replace("<br>", "\n"),
        template_data=tpl_data,
        variables={},
        tags=["public", source.name],
        is_public=False,
        created_at=now,
        updated_at=now,
    )
    session.add(template)
    await session.commit()
    await session.refresh(template)

    return {
        "id": template.id,
        "name": template.name,
        "requests": len(parsed.requests),
        "source": source.name,
        "author": meta.get("author", ""),
    }
