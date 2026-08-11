"""Request testing and cURL parsing API routes."""

import json
import shlex
import time
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from qd_core.client.fetcher import resolve_api_url

from qd_server.middleware.auth import get_current_user
from qd_server.models.user import User

router = APIRouter()


# --- Schemas ---

class TestRequest(BaseModel):
    """A single HTTP request to test."""
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"] = "GET"
    url: str = Field(min_length=1, max_length=4096)
    headers: dict[str, str] = Field(default_factory=dict)
    body: str | None = Field(default=None, max_length=1024 * 1024)
    body_type: Literal["none", "json", "form", "text"] = "none"
    timeout: int = Field(default=30, ge=1, le=120)
    verify_tls: bool = True


class TestResponse(BaseModel):
    """Response from a test request."""
    status_code: int
    headers: dict[str, str]
    body: str
    elapsed_ms: float
    error: str | None = None


class CurlParseRequest(BaseModel):
    """cURL command to parse."""
    curl_command: str


class ParsedRequest(BaseModel):
    """Parsed request from cURL or HAR."""
    method: str
    url: str
    headers: dict[str, str] = Field(default_factory=dict)
    body: str | None = None
    body_type: str = "none"
    name: str | None = None  # Request name/comment
    success_asserts: list[dict] | None = None  # QD v1 success conditions
    failed_asserts: list[dict] | None = None  # QD v1 failed conditions
    extract_variables: list[dict] | None = None  # QD v1 extractors
    checked: bool = True


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
    try:
        headers = {**request.headers}
        content = None

        if request.body and request.body_type != "none":
            if request.body_type == "json":
                headers["Content-Type"] = "application/json"
                content = request.body.encode()
            elif request.body_type == "form":
                headers["Content-Type"] = "application/x-www-form-urlencoded"
                content = request.body.encode()
            elif request.body_type == "text":
                content = request.body.encode()

        is_internal_api = request.url.lower().startswith("api://")
        resolved_url = resolve_api_url(request.url, str(http_request.base_url))
        client_options = {
            "timeout": request.timeout,
            "follow_redirects": True,
            "verify": request.verify_tls,
        }
        if is_internal_api:
            client_options["transport"] = httpx.ASGITransport(app=http_request.app)

        started = time.perf_counter()
        async with httpx.AsyncClient(
            **client_options,
        ) as client:
            async with client.stream(
                method=request.method.upper(),
                url=resolved_url,
                headers=headers,
                content=content,
            ) as response:
                resp_headers = dict(response.headers)
                body = bytearray()
                truncated = False
                async for chunk in response.aiter_bytes():
                    remaining = 50000 - len(body)
                    if remaining <= 0:
                        truncated = True
                        break
                    body.extend(chunk[:remaining])
                    if len(chunk) > remaining:
                        truncated = True
                        break
                encoding = response.encoding or "utf-8"
                body_text = bytes(body).decode(encoding, errors="replace")
                if truncated:
                    body_text += "\n... (truncated)"

            return TestResponse(
                status_code=response.status_code,
                headers=resp_headers,
                body=body_text,
                elapsed_ms=(time.perf_counter() - started) * 1000,
            )

    except httpx.TimeoutException:
        return TestResponse(
            status_code=0,
            headers={},
            body="",
            elapsed_ms=request.timeout * 1000,
            error="Request timed out",
        )
    except Exception as e:
        return TestResponse(
            status_code=0,
            headers={},
            body="",
            elapsed_ms=0,
            error=str(e),
        )


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

        # Extract headers
        headers = {}
        for h in req.get("headers", []):
            headers[h.get("name", "")] = h.get("value", "")

        # Extract body
        body = None
        body_type = "none"
        post_data = req.get("postData", {})
        if post_data:
            body = post_data.get("text")
            mime = post_data.get("mimeType", "")
            if "json" in mime:
                body_type = "json"
            elif "form" in mime:
                body_type = "form"
            else:
                body_type = "text"
        elif req.get("body"):
            body = req.get("body")
            body_type = "text"

        # Extract rule conditions
        rule = item.get("rule", {})
        success_asserts = rule.get("success_asserts", [])
        failed_asserts = rule.get("failed_asserts", [])
        extract_variables = rule.get("extract_variables", [])

        parsed.append(ParsedRequest(
            method=method,
            url=url,
            headers=headers,
            body=body,
            body_type=body_type,
            name=comment,
            success_asserts=success_asserts if success_asserts else None,
            failed_asserts=failed_asserts if failed_asserts else None,
            extract_variables=extract_variables if extract_variables else None,
            checked=item.get("checked", req.get("checked", True)),
        ))

    return parsed


def _parse_standard_har(entries: list) -> list[ParsedRequest]:
    """Parse standard HAR 1.2 format."""
    parsed = []
    for entry in entries:
        har_req = entry.get("request", {})
        method = har_req.get("method", "GET")
        url = har_req.get("url", "")

        # Extract headers
        headers = {}
        for h in har_req.get("headers", []):
            headers[h.get("name", "")] = h.get("value", "")

        # Extract body
        body = None
        body_type = "none"
        post_data = har_req.get("postData", {})
        if post_data:
            body_type = post_data.get("mimeType", "text")
            body = post_data.get("text")
            if "json" in body_type:
                body_type = "json"
            elif "form" in body_type:
                body_type = "form"
            else:
                body_type = "text"

        parsed.append(ParsedRequest(
            method=method,
            url=url,
            headers=headers,
            body=body,
            body_type=body_type,
            checked=entry.get("checked", har_req.get("checked", True)),
        ))

    return parsed
