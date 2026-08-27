"""Request testing and cURL parsing API routes."""

import json
import shlex
from typing import Any, Literal
from urllib.parse import urlencode, urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException, Path, Request
from pydantic import BaseModel, Field
from qd_core.client.fetcher import QDFetcher
from qd_core.config import QDCoreSettings
from qd_core.schemas.har import HARCookie, HARHeader, HARPostData, HARRequest, RequestRule

from qd_server.middleware.auth import get_current_user
from qd_server.models.user import User
from qd_server.services.test_sessions import TestSessionState, test_session_store

router = APIRouter()


# --- Schemas ---

class TestRequest(BaseModel):
    """A single HTTP request to test."""
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"] = "GET"
    url: str = Field(min_length=1, max_length=4096)
    headers: dict[str, str] = Field(default_factory=dict)
    body: str | None = Field(default=None, max_length=1024 * 1024)
    body_type: Literal["none", "json", "form", "text"] = "none"
    mime_type: str | None = Field(default=None, max_length=255)
    timeout: int = Field(default=30, ge=1, le=120)
    verify_tls: bool = True
    variables: dict[str, Any] = Field(default_factory=dict)
    proxy: str | None = Field(default=None, max_length=2048)
    session_id: str | None = Field(default=None, min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    header_list: list[HARHeader] | None = None
    cookies: list[HARCookie] = Field(default_factory=list)
    extractors: dict[str, str] = Field(default_factory=dict)
    rule: RequestRule | None = None


class TestResponse(BaseModel):
    """Response from a test request."""
    status_code: int
    headers: dict[str, str]
    body: str
    elapsed_ms: float
    error: str | None = None
    url: str = ""
    success: bool = True
    message: str = ""
    extracted_variables: dict[str, Any] = Field(default_factory=dict)
    truncated: bool = False
    session_id: str | None = None


class CurlParseRequest(BaseModel):
    """cURL command to parse."""
    curl_command: str


class ParsedRequest(BaseModel):
    """Parsed request from cURL or HAR."""
    method: str
    url: str
    headers: dict[str, str] = Field(default_factory=dict)
    header_list: list[dict[str, Any]] | None = None
    cookies: list[dict] = Field(default_factory=list)
    query_string: list[dict[str, str]] = Field(default_factory=list)
    body: str | None = None
    body_type: str = "none"
    mime_type: str | None = None
    name: str | None = None  # Request name/comment
    extractors: dict[str, str] = Field(default_factory=dict)
    success_asserts: list[dict] | None = None  # QD v1 success conditions
    failed_asserts: list[dict] | None = None  # QD v1 failed conditions
    extract_variables: list[dict] | None = None  # QD v1 extractors
    checked: bool = True
    resource_type: str = "other"
    response_set_cookie: bool = False


class HarImportRequest(BaseModel):
    """HAR file content to parse."""
    har_content: str


# --- Routes ---

@router.post("/test", response_model=TestResponse)
async def test_request(
    request: TestRequest,
    http_request: Request,
    current_user: User = Depends(get_current_user),  # noqa: B008 - FastAPI dependency
):
    """Send a test HTTP request and return the response."""
    state = (
        test_session_store.get(current_user.id, request.session_id)
        if request.session_id
        else TestSessionState()
    )
    try:
        async with state.lock:
            headers = (
                request.header_list
                if request.header_list is not None
                else [HARHeader(name=name, value=value) for name, value in request.headers.items()]
            )
            post_data = None
            if request.body is not None and request.body_type != "none":
                mime_type = request.mime_type or {
                    "json": "application/json",
                    "form": "application/x-www-form-urlencoded",
                    "text": "text/plain",
                }[request.body_type]
                post_data = HARPostData(mimeType=mime_type, text=request.body)

            har_request = HARRequest(
                method=request.method,
                url=request.url,
                headers=headers,
                cookies=request.cookies,
                postData=post_data,
                extractors=request.extractors,
                rule=request.rule,
            )
            transport = (
                httpx.ASGITransport(app=http_request.app)
                if request.url.lower().startswith("api://")
                else None
            )
            fetcher = QDFetcher(
                settings=QDCoreSettings(
                    request_timeout=request.timeout,
                    download_size_limit=50_000,
                ),
                proxy=request.proxy,
                cookie_session=state.cookies,
                api_base_url=str(http_request.base_url),
                transport=transport,
                verify_tls=request.verify_tls,
            )
            fetcher.variables.update(request.variables)
            fetcher.variables.update(state.variables)
            result = await fetcher.execute_request(har_request)
            state.variables = {
                key: value
                for key, value in fetcher.variables.items()
                if key != "_proxy"
            }

        return TestResponse(
            status_code=result["status_code"],
            headers=result["headers"],
            body=result["content"],
            elapsed_ms=result["elapsed_ms"],
            url=result["url"],
            success=result["success"],
            message=result["message"],
            extracted_variables=result["extracted_variables"],
            truncated=result["truncated"],
            session_id=request.session_id,
        )

    except httpx.TimeoutException:
        return TestResponse(
            status_code=0,
            headers={},
            body="",
            elapsed_ms=request.timeout * 1000,
            error="Request timed out",
            success=False,
            session_id=request.session_id,
        )
    except Exception as e:
        return TestResponse(
            status_code=0,
            headers={},
            body="",
            elapsed_ms=0,
            error=_safe_error_message(e, request.proxy),
            success=False,
            session_id=request.session_id,
        )


@router.delete("/sessions/{session_id}", status_code=204)
async def clear_test_session(
    session_id: str = Path(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$"),
    current_user: User = Depends(get_current_user),  # noqa: B008 - FastAPI dependency
):
    """Discard cookies and extracted variables from an editor test session."""
    test_session_store.clear(current_user.id, session_id)


def _safe_error_message(error: Exception, proxy: str | None) -> str:
    message = str(error)
    if not proxy:
        return message
    parsed = urlsplit(proxy)
    for secret in (parsed.username, parsed.password):
        if secret:
            message = message.replace(secret, "***")
    return message


@router.post("/parse-curl", response_model=ParsedRequest)
async def parse_curl(
    request: CurlParseRequest,
    current_user: User = Depends(get_current_user),  # noqa: B008 - FastAPI dependency
):
    """Parse a cURL command into a structured request."""
    try:
        return _parse_curl_command(request.curl_command)

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse cURL: {e}") from e


def _parse_curl_command(curl_command: str) -> ParsedRequest:
    """Parse common cURL request flags without executing the command."""
    cmd = curl_command.strip()
    lowered = cmd.lower()
    if lowered.startswith("curl.exe "):
        cmd = cmd[9:]
    elif lowered.startswith("curl "):
        cmd = cmd[5:]

    # Browser exports use backslashes, cmd.exe uses carets, and PowerShell uses
    # backticks for multiline commands.
    for continuation in ("\\\r\n", "\\\n", "^\r\n", "^\n", "`\r\n", "`\n"):
        cmd = cmd.replace(continuation, " ")

    parts = shlex.split(cmd)
    method = "GET"
    url = ""
    headers: dict[str, str] = {}
    body = None
    body_type = "none"

    def set_header(name: str, value: str) -> None:
        existing_name = next((key for key in headers if key.lower() == name.lower()), name)
        headers[existing_name] = value

    def append_cookie(value: str) -> None:
        cookie_name = next((key for key in headers if key.lower() == "cookie"), "Cookie")
        existing = headers.get(cookie_name)
        headers[cookie_name] = f"{existing}; {value}" if existing else value

    def set_body(value: str) -> None:
        nonlocal body, body_type, method
        body = value
        body_type = "json"
        try:
            json.loads(body)
        except (json.JSONDecodeError, TypeError):
            body_type = "form" if "=" in body else "text"
        if method == "GET":
            method = "POST"

    i = 0
    while i < len(parts):
        part = parts[i]

        if part in ("-X", "--request") and i + 1 < len(parts):
            method = parts[i + 1].upper()
            i += 2
        elif part.startswith("--request="):
            method = part.split("=", 1)[1].upper()
            i += 1
        elif part in ("-H", "--header") and i + 1 < len(parts):
            header_str = parts[i + 1]
            if ":" in header_str:
                key, value = header_str.split(":", 1)
                set_header(key.strip(), value.strip())
            i += 2
        elif part.startswith("--header="):
            header_str = part.split("=", 1)[1]
            if ":" in header_str:
                key, value = header_str.split(":", 1)
                set_header(key.strip(), value.strip())
            i += 1
        elif part in ("-b", "--cookie") and i + 1 < len(parts):
            append_cookie(parts[i + 1])
            i += 2
        elif part.startswith("--cookie="):
            append_cookie(part.split("=", 1)[1])
            i += 1
        elif part.startswith("-b") and len(part) > 2:
            append_cookie(part[2:])
            i += 1
        elif part in ("-c", "--cookie-jar") and i + 1 < len(parts):
            i += 2
        elif part.startswith("--cookie-jar="):
            i += 1
        elif part in ("-d", "--data", "--data-raw", "--data-binary") and i + 1 < len(parts):
            set_body(parts[i + 1])
            i += 2
        elif any(part.startswith(f"{flag}=") for flag in ("--data", "--data-raw", "--data-binary")):
            set_body(part.split("=", 1)[1])
            i += 1
        elif part in ("--url",) and i + 1 < len(parts):
            url = parts[i + 1]
            i += 2
        elif part.startswith("--url="):
            url = part.split("=", 1)[1]
            i += 1
        elif part == "--compressed":
            set_header("Accept-Encoding", "gzip, deflate, br")
            i += 1
        elif not part.startswith("-") and not url:
            url = part
            i += 1
        else:
            i += 1

    return ParsedRequest(method=method, url=url, headers=headers, body=body, body_type=body_type)


@router.post("/parse-har", response_model=list[ParsedRequest])
async def parse_har(
    request: HarImportRequest,
    current_user: User = Depends(get_current_user),  # noqa: B008 - FastAPI dependency
):
    """Parse a HAR file and extract all requests.

    Supports both standard HAR 1.2 format and QD v1 format.
    """
    try:
        har_data = json.loads(request.har_content)

        # Detect QD v1 format: array of objects with "request" and "rule"
        if isinstance(har_data, list) and len(har_data) > 0 and "request" in har_data[0]:
            return _parse_qd_v1(har_data)

        # Standard HAR 1.2 format
        entries = har_data.get("log", {}).get("entries", [])
        return _parse_standard_har(entries)

    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON in HAR file") from exc
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse HAR: {e}") from e


def _parse_qd_v1(data: list) -> list[ParsedRequest]:
    """Parse QD v1 format (array of {comment, request, rule})."""
    parsed = []
    for item in data:
        req = item.get("request", {})
        method = req.get("method", "GET")
        url = req.get("url", "")
        comment = item.get("comment", "")

        headers, header_list = _parse_har_headers(req.get("headers", []))
        body, body_type, mime_type = _parse_har_body(req)

        # Extract rule conditions
        rule = item.get("rule", {})
        success_asserts = rule.get("success_asserts", [])
        failed_asserts = rule.get("failed_asserts", [])
        extract_variables = rule.get("extract_variables", [])

        parsed.append(ParsedRequest(
            method=method,
            url=url,
            headers=headers,
            header_list=header_list,
            cookies=_parse_har_cookies(req.get("cookies", [])),
            query_string=_parse_har_query_string(req.get("queryString", [])),
            body=body,
            body_type=body_type,
            mime_type=mime_type,
            name=comment,
            extractors=req.get("extractors", {}),
            success_asserts=success_asserts if success_asserts else None,
            failed_asserts=failed_asserts if failed_asserts else None,
            extract_variables=extract_variables if extract_variables else None,
            checked=item.get("checked", req.get("checked", True)),
            resource_type=_har_resource_type(item, req),
            response_set_cookie=_response_has_set_cookie(item.get("response")),
        ))

    return parsed


def _parse_standard_har(entries: list) -> list[ParsedRequest]:
    """Parse standard HAR 1.2 format."""
    parsed = []
    for entry in entries:
        har_req = entry.get("request", {})
        method = har_req.get("method", "GET")
        url = har_req.get("url", "")

        headers, header_list = _parse_har_headers(har_req.get("headers", []))
        body, body_type, mime_type = _parse_har_body(har_req)
        rule = entry.get("rule", {})
        success_asserts = entry.get("success_asserts", rule.get("success_asserts", []))
        failed_asserts = entry.get("failed_asserts", rule.get("failed_asserts", []))
        extract_variables = entry.get("extract_variables", rule.get("extract_variables", []))

        parsed.append(ParsedRequest(
            method=method,
            url=url,
            headers=headers,
            header_list=header_list,
            cookies=_parse_har_cookies(har_req.get("cookies", [])),
            query_string=_parse_har_query_string(har_req.get("queryString", [])),
            body=body,
            body_type=body_type,
            mime_type=mime_type,
            name=entry.get("comment") or har_req.get("comment"),
            extractors=har_req.get("extractors", {}),
            success_asserts=success_asserts or None,
            failed_asserts=failed_asserts or None,
            extract_variables=extract_variables or None,
            checked=entry.get("checked", har_req.get("checked", True)),
            resource_type=_har_resource_type(entry, har_req),
            response_set_cookie=_response_has_set_cookie(entry.get("response")),
        ))

    return parsed


def _har_resource_type(entry: dict, request: dict) -> str:
    value = (
        entry.get("_resourceType")
        or entry.get("resourceType")
        or request.get("_resourceType")
        or request.get("resourceType")
        or "other"
    )
    return str(value).strip().lower() or "other"


def _response_has_set_cookie(response: Any) -> bool:
    if not isinstance(response, dict):
        return False
    return any(
        isinstance(header, dict) and str(header.get("name", "")).lower() == "set-cookie"
        for header in response.get("headers", [])
    )


def _parse_har_headers(raw_headers: list) -> tuple[dict[str, str], list[dict[str, Any]]]:
    headers: dict[str, str] = {}
    header_list: list[dict[str, Any]] = []
    for raw_header in raw_headers:
        if not isinstance(raw_header, dict):
            continue
        name = str(raw_header.get("name", ""))
        if not name:
            continue
        value = str(raw_header.get("value", ""))
        checked = (
            raw_header.get("checked", True) is not False
            and not name.startswith(":")
            and name.lower() != "authority"
        )
        if checked:
            headers[name] = value
        header_list.append({"name": name, "value": value, "checked": checked})
    return headers, header_list


def _parse_har_cookies(raw_cookies: list) -> list[dict]:
    return [dict(cookie) for cookie in raw_cookies if isinstance(cookie, dict) and cookie.get("name")]


def _parse_har_query_string(raw_query: list) -> list[dict[str, str]]:
    return [
        {"name": str(query.get("name", "")), "value": str(query.get("value", ""))}
        for query in raw_query
        if isinstance(query, dict) and query.get("name")
    ]


def _parse_har_body(request: dict) -> tuple[str | None, str, str | None]:
    post_data = request.get("postData")
    body: str | None = None
    mime_type: str | None = None

    if isinstance(post_data, dict):
        mime_type = post_data.get("mimeType") or None
        if "text" in post_data:
            raw_body = post_data.get("text")
            body = "" if raw_body is None else str(raw_body)
        elif mime_type and "application/x-www-form-urlencoded" in mime_type.lower():
            params = post_data.get("params") or []
            body = urlencode([
                (str(param.get("name", "")), str(param.get("value", "")))
                for param in params
                if isinstance(param, dict) and param.get("name")
            ])
    elif "data" in request:
        raw_body = request.get("data")
        body = "" if raw_body is None else str(raw_body)
        mime_type = request.get("mimeType") or None
    elif "body" in request:
        raw_body = request.get("body")
        body = "" if raw_body is None else str(raw_body)
        mime_type = request.get("mimeType") or None

    if not mime_type:
        for header in request.get("headers", []):
            if isinstance(header, dict) and str(header.get("name", "")).lower() == "content-type":
                mime_type = str(header.get("value", "")) or None
                break

    if body is None:
        return None, "none", mime_type

    normalized_mime = (mime_type or "").lower()
    if "json" in normalized_mime:
        body_type = "json"
    elif "application/x-www-form-urlencoded" in normalized_mime:
        body_type = "form"
    else:
        body_type = "text"
    return body, body_type, mime_type
