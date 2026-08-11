"""HTTP fetcher for QD2.

Async HTTP client that executes HAR template requests with QD v1 compatible
Jinja2 rendering, success/failed asserts, and variable extraction.
"""

import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from qd_core.client.cookie_session import CookieSession
from qd_core.client.render import render_string
from qd_core.client.rule import run_rule
from qd_core.config import QDCoreSettings
from qd_core.schemas.har import HARRequest, HARTemplate
from qd_core.utils.log import Log

logger = Log("QD.Core.Fetcher").getlogger()

SUPPORTED_UTIL_PATHS = {
    "/timestamp",
    "/unicode",
    "/gb2312",
    "/urldecode",
    "/regex",
    "/string/replace",
    "/rsa",
}


def resolve_api_url(url: str, api_base_url: str | None) -> str:
    """Resolve the QD v1 ``api://util/*`` scheme to the local utility API."""
    parsed = urlsplit(url)
    if parsed.scheme.lower() != "api":
        return url
    if parsed.netloc.lower() != "util":
        raise ValueError(f"Unsupported api:// service: {parsed.netloc or '(empty)'}")
    if not api_base_url:
        raise ValueError("api:// URL requires a configured QD API base URL")

    util_path = parsed.path or ""
    is_delay_path = util_path == "/delay" or re.fullmatch(r"/delay/[^/]+", util_path)
    if util_path not in SUPPORTED_UTIL_PATHS and not is_delay_path:
        raise ValueError(f"Unsupported api://util path: {util_path or '/'}")

    base = urlsplit(api_base_url.rstrip("/"))
    path = f"/util{util_path}"
    return urlunsplit((base.scheme, base.netloc, path, parsed.query, ""))


class QDFetcher:
    """Async HTTP client for executing QD2 templates.

    Features:
    - Jinja2 variable rendering (QD v1 filter compatible)
    - Success/failed asserts per request (QD v1 rule engine)
    - Response data extraction (regex rules, JSON path, headers)
    - Persistent cookie session across requests and runs
    """

    def __init__(
        self,
        settings: QDCoreSettings | None = None,
        proxy: str | None = None,
        cookie_session: CookieSession | None = None,
        api_base_url: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.settings = settings or QDCoreSettings()
        self.variables: dict[str, Any] = {}
        self.session = cookie_session or CookieSession()
        self.proxy = proxy
        self.api_base_url = api_base_url
        self.transport = transport

    async def execute_template(self, template: HARTemplate) -> list[dict[str, Any]]:
        """Execute all requests in a template sequentially.

        Args:
            template: The HAR template to execute.

        Returns:
            List of response summaries for each request.
        """
        # Merge template variables with instance variables
        merged = dict(template.variables)
        merged.update(self.variables)
        self.variables = merged
        results = []

        client_kwargs: dict[str, Any] = dict(
            timeout=self.settings.request_timeout,
            follow_redirects=True,
            cookies=self.session.to_httpx_cookies(),
        )
        if self.proxy:
            client_kwargs["proxy"] = self.proxy
        if self.transport:
            client_kwargs["transport"] = self.transport

        async with httpx.AsyncClient(**client_kwargs) as client:
            for i, request in enumerate(template.requests):
                if not request.checked:
                    logger.info("Skipping unchecked request %d/%d", i + 1, len(template.requests))
                    continue
                logger.info(
                    "Executing request %d/%d: %s %s", i + 1, len(template.requests), request.method, request.url
                )

                try:
                    result = await self._execute_request(client, request, template.extractors)
                    results.append(result)

                    # Persist response cookies into the session
                    self.session.update_from_httpx(client.cookies)

                    if not result.get("success", True):
                        logger.warning("Request %d failed assert: %s", i + 1, result.get("message"))
                        break

                except Exception as e:
                    logger.error("Request %d failed: %s", i + 1, e)
                    results.append(
                        {
                            "status": "error",
                            "success": False,
                            "error": str(e),
                            "request_index": i,
                        }
                    )
                    break  # Stop on first error

        return results

    async def _execute_request(
        self,
        client: httpx.AsyncClient,
        request: HARRequest,
        global_extractors: dict[str, str],
    ) -> dict[str, Any]:
        """Execute a single HTTP request.

        Renders url/headers/body with Jinja2, executes, then runs the QD v1
        rule engine (asserts + extract_variables) followed by legacy extractors.
        """
        cookies_view = self.session

        # Render request pieces with Jinja2 (QD v1 compatible)
        url = resolve_api_url(
            render_string(request.url, self.variables, cookies_view),
            self.api_base_url,
        )

        headers = {}
        for h in request.headers:
            name = render_string(h.name, self.variables, cookies_view)
            headers[name] = render_string(h.value, self.variables, cookies_view)

        params = {}
        for q in request.queryString:
            params[render_string(q.name, self.variables, cookies_view)] = render_string(
                q.value, self.variables, cookies_view
            )

        req_cookies = {}
        for c in request.cookies:
            req_cookies[render_string(c.name, self.variables, cookies_view)] = render_string(
                c.value, self.variables, cookies_view
            )

        content = None
        if request.postData and request.postData.text:
            content = render_string(request.postData.text, self.variables, cookies_view)
            if request.postData.mimeType and not any(
                name.lower() == "content-type" for name in headers
            ):
                headers["Content-Type"] = request.postData.mimeType

        # Execute request
        response = await client.request(
            method=request.method.value,
            url=url,
            headers=headers,
            params=params or None,
            cookies=req_cookies or None,
            content=content,
        )

        # QD v1 rule engine: success/failed asserts + extract_variables
        rule_extracted: dict[str, Any] = {}
        success, message = run_rule(
            response,
            request.rule,
            self.variables,
            cookies_view,
            extracted_variables=rule_extracted,
        )

        # Legacy extractors (QD2 early format). A QD v1 rule is authoritative
        # when both formats declare the same variable (older editor versions
        # persisted every extractor in both places).
        rule_variable_names = (
            {extractor.name for extractor in request.rule.extract_variables}
            if request.rule
            else set()
        )
        legacy_extracted = self._extract_variables(
            response,
            request.extractors,
            global_extractors,
            excluded_names=rule_variable_names,
        )
        self.variables.update(legacy_extracted)
        extracted = {**legacy_extracted, **rule_extracted}

        return {
            "status": "success" if success else "failed",
            "success": success,
            "message": message,
            "status_code": response.status_code,
            "url": str(response.url),
            "headers": dict(response.headers),
            "content": response.text[: self.settings.download_size_limit]
            if hasattr(self.settings, "download_size_limit")
            else response.text,
            "extracted_variables": extracted,
        }

    def _extract_variables(
        self,
        response: httpx.Response,
        request_extractors: dict[str, str],
        global_extractors: dict[str, str],
        excluded_names: set[str] | None = None,
    ) -> dict[str, Any]:
        """Extract variables from response using legacy extractors."""
        extracted = {}
        all_extractors = {**global_extractors, **request_extractors}

        for var_name, extractor_expr in all_extractors.items():
            if excluded_names and var_name in excluded_names:
                continue
            try:
                value = self._resolve_extractor(response, extractor_expr)
                extracted[var_name] = value
                logger.debug("Extracted variable '%s' = %s", var_name, value)
            except Exception as e:
                logger.warning("Failed to extract variable '%s': %s", var_name, e)

        return extracted

    def _resolve_extractor(self, response: httpx.Response, expression: str) -> Any:
        """Resolve an extractor expression against a response."""
        # Regex extractor: regex:pattern
        if expression.startswith("regex:"):
            match = re.search(expression[6:], response.text)
            if match is None:
                return None
            return match.group(1) if match.groups() else match.group(0)

        # Header extractor: header:Header-Name
        if expression.startswith("header:"):
            header_name = expression[7:]
            return response.headers.get(header_name)

        # Status code extractor
        if expression == "status":
            return response.status_code

        # JSON path extractor: response.json()["key"]["subkey"]
        if expression.startswith("response.json()"):
            data = response.json()
            path = expression.replace("response.json()", "")
            return self._resolve_json_path(data, path)

        # Default: return response text
        return response.text

    def _resolve_json_path(self, data: Any, path: str) -> Any:
        """Resolve a JSON path expression like ["key"]["subkey"][0]."""
        segments = re.findall(r'\["([^"]+)"\]|\[(\d+)\]', path)

        current = data
        for key, index in segments:
            current = current[int(index)] if index else current[key]

        return current
