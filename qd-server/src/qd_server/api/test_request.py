"""Request testing and cURL parsing API routes."""

import shlex
import json
import time
from typing import Literal, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from qd_server.middleware.auth import get_current_user
from qd_server.models.user import User

router = APIRouter()


# --- Schemas ---

class TestRequest(BaseModel):
    """A single HTTP request to test."""
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"] = "GET"
    url: str = Field(min_length=1, max_length=4096)
    headers: dict[str, str] = Field(default_factory=dict)
    body: Optional[str] = Field(default=None, max_length=1024 * 1024)
    body_type: Literal["none", "json", "form", "text"] = "none"
    timeout: int = Field(default=30, ge=1, le=120)
    verify_tls: bool = True


class TestResponse(BaseModel):
    """Response from a test request."""
    status_code: int
    headers: dict[str, str]
    body: str
    elapsed_ms: float
    error: Optional[str] = None


class CurlParseRequest(BaseModel):
    """cURL command to parse."""
    curl_command: str


class ParsedRequest(BaseModel):
    """Parsed request from cURL or HAR."""
    method: str
    url: str
    headers: dict[str, str] = {}
    body: Optional[str] = None
    body_type: str = "none"
    name: Optional[str] = None  # Request name/comment
    success_asserts: Optional[list[dict]] = None  # QD v1 success conditions
    failed_asserts: Optional[list[dict]] = None  # QD v1 failed conditions
    extract_variables: Optional[list[dict]] = None  # QD v1 extractors


class HarImportRequest(BaseModel):
    """HAR file content to parse."""
    har_content: str


# --- Routes ---

@router.post("/test", response_model=TestResponse)
async def test_request(
    request: TestRequest,
    current_user: User = Depends(get_current_user),
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

        started = time.perf_counter()
        async with httpx.AsyncClient(
            timeout=request.timeout,
            follow_redirects=True,
            verify=request.verify_tls,
        ) as client:
            async with client.stream(
                method=request.method.upper(),
                url=request.url,
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
    current_user: User = Depends(get_current_user),
):
    """Parse a cURL command into a structured request."""
    try:
        # Clean up the command
        cmd = request.curl_command.strip()
        if cmd.startswith("curl "):
            cmd = cmd[5:]

        # Handle line continuations
        cmd = cmd.replace("\\\n", " ").replace("\\\r\n", " ")

        # Parse with shlex
        parts = shlex.split(cmd)

        method = "GET"
        url = ""
        headers = {}
        body = None
        body_type = "none"

        i = 0
        while i < len(parts):
            part = parts[i]

            if part in ("-X", "--request") and i + 1 < len(parts):
                method = parts[i + 1].upper()
                i += 2
            elif part in ("-H", "--header") and i + 1 < len(parts):
                header_str = parts[i + 1]
                if ":" in header_str:
                    key, value = header_str.split(":", 1)
                    headers[key.strip()] = value.strip()
                i += 2
            elif part in ("-d", "--data", "--data-raw", "--data-binary") and i + 1 < len(parts):
                body = parts[i + 1]
                body_type = "json"
                # Try to detect JSON
                try:
                    json.loads(body)
                except (json.JSONDecodeError, TypeError):
                    body_type = "form" if "=" in body and "&" in body else "text"
                if method == "GET":
                    method = "POST"
                i += 2
            elif part == "--compressed":
                headers["Accept-Encoding"] = "gzip, deflate, br"
                i += 1
            elif not part.startswith("-") and not url:
                url = part
                i += 1
            else:
                i += 1

        return ParsedRequest(
            method=method,
            url=url,
            headers=headers,
            body=body,
            body_type=body_type,
        )

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse cURL: {e}") from e


@router.post("/parse-har", response_model=list[ParsedRequest])
async def parse_har(
    request: HarImportRequest,
    current_user: User = Depends(get_current_user),
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
        ))

    return parsed
