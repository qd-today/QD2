import httpx
import pytest
from qd_core.client.cookie_session import CookieSession
from qd_core.client.fetcher import (
    QDFetcher,
    encode_form_non_ascii,
    normalize_proxy_url,
    resolve_api_url,
)
from qd_core.schemas.har import HARPostData, HARRequest, HARTemplate


@pytest.mark.asyncio
async def test_rule_extractor_takes_priority_over_duplicate_legacy_extractor() -> None:
    fetcher = QDFetcher()
    request = HARRequest.model_validate(
        {
            "method": "GET",
            "url": "https://example.test/",
            "extractors": {"__log__": "legacy-response-body"},
            "rule": {
                "extract_variables": [
                    {"name": "__log__", "re": "QD框架", "from": "content"},
                ]
            },
        }
    )
    response = httpx.Response(200, text="<html><title>QD框架</title></html>")
    transport = httpx.MockTransport(lambda _request: response)

    async with httpx.AsyncClient(transport=transport) as client:
        result = await fetcher._execute_request(client, request, {})

    assert result["extracted_variables"] == {"__log__": "QD框架"}
    assert fetcher.variables["__log__"] == "QD框架"


def test_legacy_regex_extractor_returns_capture_group() -> None:
    fetcher = QDFetcher()
    response = httpx.Response(200, text="今日签到: 12; 剩余天数: 108")

    assert fetcher._resolve_extractor(response, r"regex:今日签到: (\d+)") == "12"


def test_legacy_regex_extractor_returns_full_match_without_group() -> None:
    fetcher = QDFetcher()
    response = httpx.Response(200, text="<title>QD框架</title>")

    assert fetcher._resolve_extractor(response, "regex:QD框架") == "QD框架"


def test_resolve_api_url_only_allows_util_service() -> None:
    assert resolve_api_url(
        "api://util/delay/3?source=test",
        "http://127.0.0.1:8924/",
    ) == "http://127.0.0.1:8924/util/delay/3?source=test"
    with pytest.raises(ValueError, match="Unsupported api:// service"):
        resolve_api_url("api://admin/users", "http://127.0.0.1:8924")
    with pytest.raises(ValueError, match="Unsupported api://util path"):
        resolve_api_url("api://util/not-migrated", "http://127.0.0.1:8924")


def test_form_literal_unicode_is_encoded_without_double_encoding() -> None:
    assert encode_form_non_ascii(
        "content=你好&escaped=%5Cu4f60&value={{name|urlencode}}",
        "application/x-www-form-urlencoded",
    ) == "content=%E4%BD%A0%E5%A5%BD&escaped=%5Cu4f60&value={{name|urlencode}}"
    assert encode_form_non_ascii(
        "content=中文",
        "application/x-www-form-urlencoded; charset=gb18030",
    ) == "content=%D6%D0%CE%C4"


@pytest.mark.asyncio
async def test_execute_template_skips_unchecked_requests() -> None:
    requested_paths = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        return httpx.Response(200, text="ok")

    fetcher = QDFetcher(transport=httpx.MockTransport(handler))
    template = HARTemplate(
        name="checked-requests",
        requests=[
            HARRequest(url="https://example.test/skipped", checked=False),
            HARRequest(url="https://example.test/executed", checked=True),
        ],
    )

    results = await fetcher.execute_template(template)

    assert requested_paths == ["/executed"]
    assert len(results) == 1


@pytest.mark.asyncio
async def test_execute_template_error_includes_request_context() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    fetcher = QDFetcher(transport=httpx.MockTransport(handler))
    template = HARTemplate(
        name="failed-request",
        requests=[HARRequest(method="POST", url="https://example.test/login")],
    )

    results = await fetcher.execute_template(template)

    assert results == [
        {
            "status": "error",
            "success": False,
            "error": "connection refused",
            "request_index": 0,
            "method": "POST",
            "url": "https://example.test/login",
        }
    ]


@pytest.mark.asyncio
async def test_execute_template_uses_post_data_mime_type() -> None:
    captured_request = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return httpx.Response(200, text="ok")

    fetcher = QDFetcher(transport=httpx.MockTransport(handler))
    template = HARTemplate(
        name="form-request",
        requests=[
            HARRequest(
                method="POST",
                url="https://example.test/form",
                postData=HARPostData(
                    mimeType="application/x-www-form-urlencoded",
                    text="content=hello",
                ),
            )
        ],
    )

    results = await fetcher.execute_template(template)

    assert len(results) == 1
    assert captured_request is not None
    assert captured_request.headers["content-type"] == "application/x-www-form-urlencoded"
    assert captured_request.content == b"content=hello"


@pytest.mark.asyncio
async def test_execute_template_preserves_duplicate_request_headers() -> None:
    captured_request = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return httpx.Response(200, text="ok")

    fetcher = QDFetcher(transport=httpx.MockTransport(handler))
    template = HARTemplate(
        name="duplicate-headers",
        requests=[
            HARRequest(
                url="https://example.test/headers",
                headers=[
                    {"name": "X-Trace", "value": "first"},
                    {"name": "X-Trace", "value": "second"},
                ],
            )
        ],
    )

    await fetcher.execute_template(template)

    assert captured_request is not None
    assert captured_request.headers.get_list("x-trace") == ["first", "second"]


@pytest.mark.asyncio
async def test_execute_template_skips_disabled_and_forbidden_headers() -> None:
    captured_request = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return httpx.Response(200, text="ok")

    fetcher = QDFetcher(transport=httpx.MockTransport(handler))
    template = HARTemplate(
        name="checked-headers",
        requests=[
            HARRequest(
                url="https://example.test/headers",
                headers=[
                    {"name": "X-Enabled", "value": "yes"},
                    {"name": "X-Disabled", "value": "no", "checked": False},
                    {"name": "authority", "value": "example.test"},
                    {"name": ":authority", "value": "example.test"},
                    {"name": ":method", "value": "GET"},
                    {"name": ":path", "value": "/headers"},
                    {"name": ":scheme", "value": "https"},
                ],
            )
        ],
    )

    await fetcher.execute_template(template)

    assert captured_request is not None
    assert captured_request.headers["x-enabled"] == "yes"
    assert "x-disabled" not in captured_request.headers
    assert "authority" not in captured_request.headers


@pytest.mark.asyncio
async def test_execute_request_reuses_cookie_session() -> None:
    captured_cookie = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_cookie
        if request.url.path == "/set-cookie":
            return httpx.Response(200, headers={"Set-Cookie": "token=abc123; Path=/"}, text="set")
        captured_cookie = request.headers.get("cookie")
        return httpx.Response(200, text="read")

    fetcher = QDFetcher(transport=httpx.MockTransport(handler))

    await fetcher.execute_request(HARRequest(url="https://example.test/set-cookie"))
    await fetcher.execute_request(HARRequest(url="https://example.test/read"))

    assert captured_cookie == "token=abc123"


@pytest.mark.asyncio
async def test_execute_request_updates_provided_empty_cookie_session() -> None:
    captured_cookie = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_cookie
        if request.url.path == "/login":
            return httpx.Response(200, headers={"Set-Cookie": "session=logged-in; Path=/"})
        captured_cookie = request.headers.get("cookie")
        return httpx.Response(200, text="ok")

    shared_session = CookieSession()
    transport = httpx.MockTransport(handler)

    await QDFetcher(cookie_session=shared_session, transport=transport).execute_request(
        HARRequest(url="https://example.test/login")
    )
    await QDFetcher(cookie_session=shared_session, transport=transport).execute_request(
        HARRequest(url="https://example.test/account")
    )

    assert shared_session.get("session") == "logged-in"
    assert captured_cookie == "session=logged-in"


@pytest.mark.asyncio
async def test_execute_request_injects_proxy_runtime_variable() -> None:
    captured_url = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_url
        captured_url = str(request.url)
        return httpx.Response(200, text="ok")

    fetcher = QDFetcher(
        proxy="http://proxy.example:8080",
        transport=httpx.MockTransport(handler),
    )

    await fetcher.execute_request(HARRequest(url="https://example.test/?proxy={{_proxy|urlencode}}"))

    assert captured_url == "https://example.test/?proxy=http%3A//proxy.example%3A8080"


@pytest.mark.parametrize("proxy", ["ftp://proxy.example:21", "http:///missing-host", "not-a-url"])
def test_normalize_proxy_url_rejects_invalid_values(proxy: str) -> None:
    with pytest.raises(ValueError, match="Invalid proxy URL"):
        normalize_proxy_url(proxy)


@pytest.mark.asyncio
async def test_fetcher_enforces_task_request_limit() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="ok")

    fetcher = QDFetcher(
        transport=httpx.MockTransport(handler),
        request_limit=1,
    )
    request = HARRequest(url="https://example.test/limited")

    await fetcher.execute_request(request)

    with pytest.raises(RuntimeError, match="task request limit exceeded"):
        await fetcher.execute_request(request)
