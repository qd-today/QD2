import httpx
import pytest
from qd_core.client.fetcher import QDFetcher, resolve_api_url
from qd_core.schemas.har import HARRequest, HARTemplate


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
