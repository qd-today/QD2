"""HAR (HTTP Archive) template schemas.

Defines the data models for HAR-based request templates used by QD2.
Based on the HAR 1.2 specification with QD2 extensions.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class HTTPMethod(str, Enum):
    """HTTP request methods."""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"


class HARHeader(BaseModel):
    """A single HTTP header."""

    name: str
    value: str


class HARCookie(BaseModel):
    """A single HTTP cookie."""

    name: str
    value: str
    path: Optional[str] = None
    domain: Optional[str] = None
    expires: Optional[str] = None
    httpOnly: Optional[bool] = None
    secure: Optional[bool] = None


class HARQueryParameter(BaseModel):
    """A URL query parameter."""

    name: str
    value: str


class AssertRule(BaseModel):
    """QD v1 compatible assert rule.

    ``re`` is a regex pattern (may itself contain Jinja2 template syntax);
    ``from`` (aliased ``from_``) selects the data source:
    'content' | 'status' | 'header' | 'header-<Name>'.
    """

    re: str = ""
    from_: str = Field(default="content", alias="from")

    model_config = {"populate_by_name": True}


class ExtractRule(BaseModel):
    """QD v1 compatible variable extraction rule.

    Supports ``/pattern/flags`` syntax (g/i/m/s/u) in ``re``.
    """

    name: str
    re: str = ""
    from_: str = Field(default="content", alias="from")

    model_config = {"populate_by_name": True}


class RequestRule(BaseModel):
    """Per-request rule block (QD v1 ``rule`` on each entry)."""

    success_asserts: list[AssertRule] = Field(default_factory=list)
    failed_asserts: list[AssertRule] = Field(default_factory=list)
    extract_variables: list[ExtractRule] = Field(default_factory=list)


class HARPostData(BaseModel):
    """Request body data."""

    mimeType: str = "application/x-www-form-urlencoded"
    params: Optional[list[HARHeader]] = None
    text: Optional[str] = None


class HARRequest(BaseModel):
    """A single HTTP request in HAR format.

    This is the core request definition that QD2 uses to replay HTTP requests.
    """

    method: HTTPMethod = HTTPMethod.GET
    url: str
    httpVersion: str = "HTTP/1.1"
    cookies: list[HARCookie] = Field(default_factory=list)
    headers: list[HARHeader] = Field(default_factory=list)
    queryString: list[HARQueryParameter] = Field(default_factory=list)
    postData: Optional[HARPostData] = None
    headersSize: int = -1
    bodySize: int = -1

    # QD2 extensions
    variables: dict[str, Any] = Field(
        default_factory=dict,
        description="Template variables extracted from this request",
    )
    extractors: dict[str, str] = Field(
        default_factory=dict,
        description="Response data extractors: {variable_name: json_path_or_regex}",
    )
    rule: Optional[RequestRule] = Field(
        default=None,
        description="QD v1 compatible rule block: success/failed asserts + extract_variables",
    )


class HARResponse(BaseModel):
    """A single HTTP response in HAR format."""

    status: int
    statusText: str = ""
    httpVersion: str = "HTTP/1.1"
    cookies: list[HARCookie] = Field(default_factory=list)
    headers: list[HARHeader] = Field(default_factory=list)
    content: dict[str, Any] = Field(default_factory=dict)
    redirectURL: str = ""
    headersSize: int = -1
    bodySize: int = -1


class HAREntry(BaseModel):
    """A single request/response pair in HAR format."""

    startTime: Optional[datetime] = None
    time: float = 0
    request: HARRequest
    response: Optional[HARResponse] = None
    cache: dict[str, Any] = Field(default_factory=dict)
    timings: dict[str, Any] = Field(default_factory=dict)


class HARTemplate(BaseModel):
    """QD2 HAR template - the primary unit of work.

    A template contains one or more HTTP requests that will be executed
    in sequence, with variable extraction and substitution between requests.
    """

    name: str
    description: str = ""
    version: str = "1.0"

    # Template variables (user-defined, can be overridden at runtime)
    variables: dict[str, Any] = Field(default_factory=dict)

    # Variable extraction rules from responses
    extractors: dict[str, str] = Field(
        default_factory=dict,
        description="Global extractors applied to all responses",
    )

    # Requests to execute in order
    requests: list[HARRequest] = Field(default_factory=list)

    # Metadata
    author: str = ""
    tags: list[str] = Field(default_factory=list)
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None

    # Scheduling (optional, mainly for UI display)
    enabled: bool = True


class HARData(BaseModel):
    """Full HAR 1.2 compatible data structure.

    Wraps a HARTemplate with standard HAR metadata for import/export.
    """

    log: dict[str, Any] = Field(default_factory=dict)
    template: Optional[HARTemplate] = None
