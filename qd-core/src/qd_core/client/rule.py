"""QD v1 compatible rule engine — success/failed asserts + variable extraction.

Port of ``Fetcher.run_rule`` from original QD ``libs/fetcher.py``, adapted to
httpx responses.
"""

import base64
import re
from typing import Any, Optional

import httpx

from qd_core.client.render import RenderError, render_string
from qd_core.schemas.har import RequestRule
from qd_core.utils.log import Log

logger = Log("QD.Core.Rule").getlogger()


def _get_data(response: httpx.Response, _from: str) -> str:
    """Extract the data source selected by an assert/extract rule."""
    if _from == "content":
        content_type = response.headers.get("content-type", "")
        if "image" in content_type:
            return base64.b64encode(response.content).decode("utf8")
        return response.text
    if _from == "status":
        return f"{response.status_code}"
    if _from.startswith("header-"):
        header_name = _from[7:]
        return response.headers.get(header_name, "")
    if _from == "header":
        return "\n".join(f"{key}: {value}" for key, value in response.headers.items())
    return ""


def run_rule(
    response: httpx.Response,
    rule: Optional[RequestRule],
    variables: dict[str, Any],
    cookies: Any = None,
) -> tuple[bool, str]:
    """Evaluate success/failed asserts and extract variables from a response.

    Mutates ``variables`` in place with extracted values (QD v1 behaviour).

    Returns:
        (success, message) tuple.
    """
    success = True
    msg = ""

    if rule is None:
        return success, msg

    def _render(pattern: str) -> str:
        if not pattern:
            return pattern
        try:
            return render_string(pattern, variables, cookies)
        except RenderError:
            # keep original pattern if it isn't valid Jinja2 (e.g. regex braces)
            return pattern

    # --- success asserts: at least one must match ---
    matched_any = False
    for r in rule.success_asserts:
        pattern = _render(r.re)
        if pattern and re.search(pattern, _get_data(response, r.from_)):
            msg = ""
            matched_any = True
            break
        msg = f"Fail assert: {{'re': {r.re!r}, 'from': {r.from_!r}}} from success_asserts"
    if rule.success_asserts and not matched_any:
        success = False

    # --- failed asserts: any match ⇒ failure ---
    for r in rule.failed_asserts:
        pattern = _render(r.re)
        if pattern and re.search(pattern, _get_data(response, r.from_)):
            success = False
            msg = f"Fail assert: {{'re': {r.re!r}, 'from': {r.from_!r}}} from failed_asserts"
            break

    if not success and msg and response.status_code >= 400:
        msg += f", \\r\\nResponse Error : {response.status_code} {response.reason_phrase}"

    # --- variable extraction (supports /pattern/flags syntax) ---
    for r in rule.extract_variables:
        pattern = r.re
        flags = 0
        find_all = False

        re_m = re.match(r"^/(.*?)/([gimsu]*)$", r.re)
        if re_m:
            pattern = re_m.group(1)
            flag_str = re_m.group(2)
            if "g" in flag_str:
                find_all = True
            if "i" in flag_str:
                flags |= re.I
            if "m" in flag_str:
                flags |= re.M
            if "s" in flag_str:
                flags |= re.S
            if "u" in flag_str:
                flags |= re.U

        data = _get_data(response, r.from_)
        if find_all:
            try:
                variables[r.name] = re.compile(pattern, flags).findall(data)
            except Exception as e:
                variables[r.name] = str(e)
        else:
            try:
                m = re.compile(pattern, flags).search(data)
                if m:
                    variables[r.name] = m.groups()[0] if m.groups() else m.group(0)
            except Exception as e:
                variables[r.name] = str(e)

    return success, msg
