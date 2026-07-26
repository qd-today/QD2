"""Template rendering for QD2 — Jinja2 sandboxed engine, QD v1 compatible.

Replaces simple ``{{var}}`` string substitution with a real Jinja2
SandboxedEnvironment loaded with the full original-QD filter set, so
original QD templates (using filters like ``| md5``, ``| urlencode``,
``| timestamp()`` etc.) render identically.
"""

from typing import Any, Optional

from jinja2.sandbox import SandboxedEnvironment

from qd_core.client.har import HARParser
from qd_core.filters.jinja_filters import jinja_globals, jinja_inner_globals
from qd_core.schemas.har import HARTemplate
from qd_core.utils.log import Log

logger = Log("QD.Core.Render").getlogger()


class RenderError(Exception):
    """Raised when a template string fails to render."""


def make_jinja_env() -> SandboxedEnvironment:
    """Create a sandboxed Jinja2 environment with QD-compatible filters/globals."""
    env = SandboxedEnvironment()
    env.globals.update(jinja_globals)
    env.globals.update(jinja_inner_globals)
    env.filters.update(jinja_globals)
    return env


# Shared environment — thread-safe for rendering (no autoescape state mutation)
_jinja_env: Optional[SandboxedEnvironment] = None


def get_jinja_env() -> SandboxedEnvironment:
    global _jinja_env
    if _jinja_env is None:
        _jinja_env = make_jinja_env()
    return _jinja_env


def render_string(text: str, variables: dict[str, Any], cookies: Any = None) -> str:
    """Render a single template string with Jinja2.

    Args:
        text: Template text (may contain {{var}}, {% %}, filters, etc.)
        variables: Variables available during rendering.
        cookies: Optional cookie session exposed as ``_cookies`` (QD v1 compat).

    Returns:
        Rendered string.

    Raises:
        RenderError: If rendering fails (syntax error, undefined filter, etc.)
    """
    if not text:
        return text
    env = get_jinja_env()
    try:
        return env.from_string(text).render(_cookies=cookies if cookies is not None else {}, **variables)
    except Exception as e:
        msg = f"The error occurred when rendering template: {text!r} \\r\\n {e!r}"
        raise RenderError(msg) from e


def render_template(
    template: HARTemplate,
    variables: dict[str, Any] | None = None,
    cookies: Any = None,
) -> HARTemplate:
    """Render a template with the given variables.

    Creates a new template with all variable references resolved via Jinja2.

    Args:
        template: The template to render.
        variables: Variables to substitute (merged with template defaults).
        cookies: Optional cookie session exposed as ``_cookies``.

    Returns:
        A new HARTemplate with variables resolved.
    """
    merged_vars = {**template.variables}
    if variables:
        merged_vars.update(variables)

    rendered_requests = []
    for req in template.requests:
        rendered_req = req.model_copy(deep=True)
        rendered_req.url = render_string(req.url, merged_vars, cookies)

        for header in rendered_req.headers:
            header.value = render_string(header.value, merged_vars, cookies)

        for cookie in rendered_req.cookies:
            cookie.value = render_string(cookie.value, merged_vars, cookies)

        if rendered_req.postData and rendered_req.postData.text:
            rendered_req.postData.text = render_string(rendered_req.postData.text, merged_vars, cookies)

        rendered_requests.append(rendered_req)

    rendered = template.model_copy(deep=True)
    rendered.requests = rendered_requests
    rendered.variables = merged_vars

    return rendered


# Backwards-compatible alias used by older call sites
def substitute_variables(text: str, variables: dict[str, Any]) -> str:
    """Jinja2-based replacement for HARParser.substitute_variables."""
    try:
        return render_string(text, variables)
    except RenderError:
        # Fall back to legacy simple substitution on syntax errors so that
        # payloads containing literal '{{' (e.g. JS code) don't break.
        return HARParser.substitute_variables(text, variables)
