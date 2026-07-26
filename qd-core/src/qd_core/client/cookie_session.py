"""Cookie session management for QD2 tasks.

JSON-serializable cookie jar compatible with original QD's CookieSession
(``libs/cookie_utils.py``) dump format, adapted for httpx.
"""

import time
from http.cookiejar import Cookie, CookieJar
from typing import Any, Optional

import httpx

from qd_core.utils.log import Log

logger = Log("QD.Core.CookieSession").getlogger()

# Fields serialized for each cookie — matches original QD dump_cookie()
_COOKIE_FIELDS = (
    "name",
    "value",
    "expires",
    "secure",
    "port",
    "domain",
    "path",
    "discard",
    "comment",
    "comment_url",
    "rfc2109",
)


def dump_cookie(cookie: Cookie) -> dict[str, Any]:
    """Serialize a Cookie object into a dict (original QD compatible)."""
    result = {}
    for key in _COOKIE_FIELDS:
        result[key] = getattr(cookie, key, None)
    result["rest"] = getattr(cookie, "_rest", {})  # pylint: disable=protected-access
    return result


def make_cookie(
    name: str,
    value: str,
    domain: str = "",
    path: str = "/",
    expires: Optional[int] = None,
    secure: bool = False,
    port: Optional[str] = None,
    discard: bool = True,
    comment: Optional[str] = None,
    comment_url: Optional[str] = None,
    rfc2109: bool = False,
    rest: Optional[dict] = None,
) -> Cookie:
    """Create an http.cookiejar.Cookie from plain values."""
    return Cookie(
        version=0,
        name=name,
        value=value,
        port=port,
        port_specified=bool(port),
        domain=domain or "",
        domain_specified=bool(domain),
        domain_initial_dot=bool(domain) and domain.startswith("."),
        path=path or "/",
        path_specified=bool(path),
        secure=bool(secure),
        expires=expires,
        discard=discard,
        comment=comment,
        comment_url=comment_url,
        rest=rest or {"HttpOnly": None},
        rfc2109=rfc2109,
    )


class CookieSession:
    """A JSON-serializable cookie session for task execution.

    Wraps httpx.Cookies so it can be handed straight to httpx.AsyncClient,
    while supporting the original QD dump format for DB persistence.
    """

    def __init__(self) -> None:
        self.jar = CookieJar()

    # --- (de)serialization -------------------------------------------------

    def from_json(self, data: list[dict[str, Any]] | None) -> "CookieSession":
        """Load cookies from a list of dicts (original QD format)."""
        if not data:
            return self
        for item in data:
            try:
                kwargs = {k: item.get(k) for k in (
                    "name", "value", "domain", "path", "expires", "secure",
                    "port", "discard", "comment", "comment_url", "rfc2109",
                )}
                kwargs["rest"] = item.get("rest") or {}
                # tolerate missing name/value
                if not kwargs.get("name"):
                    continue
                kwargs["value"] = kwargs.get("value") or ""
                self.jar.set_cookie(make_cookie(**kwargs))
            except Exception as e:
                logger.warning("Skipping malformed cookie %s: %s", item.get("name"), e)
        return self

    def to_json(self) -> list[dict[str, Any]]:
        """Dump all cookies to a list of dicts (original QD format)."""
        return [dump_cookie(c) for c in self.jar]

    # --- httpx integration -------------------------------------------------

    def to_httpx_cookies(self) -> httpx.Cookies:
        """Convert to httpx.Cookies for client usage."""
        cookies = httpx.Cookies()
        now = time.time()
        for c in self.jar:
            if c.expires and c.expires < now:
                continue  # skip expired
            cookies.set(c.name, c.value or "", domain=c.domain or "", path=c.path or "/")
        return cookies

    def update_from_httpx(self, cookies: httpx.Cookies) -> None:
        """Merge cookies from an httpx client back into this session."""
        for c in cookies.jar:
            self.jar.set_cookie(c)

    # --- dict-like helpers (used by templates via _cookies) ----------------

    def get(self, name: str, default: Any = None) -> Any:
        for c in self.jar:
            if c.name == name:
                return c.value
        return default

    def __getitem__(self, name: str) -> Any:
        value = self.get(name, None)
        if value is None:
            raise KeyError(name)
        return value

    def __contains__(self, name: str) -> bool:
        return self.get(name, None) is not None

    def keys(self):
        return [c.name for c in self.jar]

    def to_dict(self) -> dict[str, str]:
        return {c.name: (c.value or "") for c in self.jar}

    def set(self, name: str, value: str, domain: str = "", path: str = "/") -> None:
        self.jar.set_cookie(make_cookie(name=name, value=value, domain=domain, path=path))

    def clear(self) -> None:
        self.jar.clear()

    def __len__(self) -> int:
        return len(self.jar)

    def __repr__(self) -> str:
        return f"<CookieSession {len(self.jar)} cookies>"
