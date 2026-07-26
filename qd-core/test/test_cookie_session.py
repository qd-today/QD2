"""Tests for the persistent CookieSession."""

import httpx

from qd_core.client.cookie_session import CookieSession


class TestSerialization:
    def test_roundtrip(self):
        cs = CookieSession()
        cs.set("token", "abc123", domain="example.com", path="/")
        cs.set("sid", "xyz", domain="example.com")

        data = cs.to_json()
        assert len(data) == 2
        assert {d["name"] for d in data} == {"token", "sid"}

        cs2 = CookieSession().from_json(data)
        assert cs2.get("token") == "abc123"
        assert cs2.get("sid") == "xyz"

    def test_from_json_empty(self):
        cs = CookieSession().from_json(None)
        assert len(cs) == 0
        cs = CookieSession().from_json([])
        assert len(cs) == 0

    def test_from_json_malformed_skipped(self):
        cs = CookieSession().from_json([
            {"name": "good", "value": "v", "domain": "x.com", "path": "/"},
            {"value": "no-name"},  # missing name → skipped
        ])
        assert len(cs) == 1
        assert cs.get("good") == "v"

    def test_original_qd_dump_format(self):
        """Must accept the exact dict shape original QD dump_cookie produces."""
        original_dump = [{
            "name": "session_id",
            "value": "deadbeef",
            "expires": None,
            "secure": False,
            "port": None,
            "domain": "linux.do",
            "path": "/",
            "discard": True,
            "comment": None,
            "comment_url": None,
            "rfc2109": False,
            "rest": {"HttpOnly": None},
        }]
        cs = CookieSession().from_json(original_dump)
        assert cs.get("session_id") == "deadbeef"
        # roundtrip preserves fields
        out = cs.to_json()[0]
        assert out["name"] == "session_id"
        assert out["domain"] == "linux.do"


class TestDictInterface:
    def test_getitem(self):
        cs = CookieSession()
        cs.set("k", "v")
        assert cs["k"] == "v"

    def test_getitem_missing_raises(self):
        cs = CookieSession()
        try:
            _ = cs["nope"]
            raise AssertionError("expected KeyError")
        except KeyError:
            pass

    def test_contains_keys_to_dict(self):
        cs = CookieSession()
        cs.set("a", "1")
        cs.set("b", "2")
        assert "a" in cs
        assert "c" not in cs
        assert set(cs.keys()) == {"a", "b"}
        assert cs.to_dict() == {"a": "1", "b": "2"}

    def test_clear(self):
        cs = CookieSession()
        cs.set("a", "1")
        cs.clear()
        assert len(cs) == 0


class TestHttpxIntegration:
    def test_to_httpx_cookies(self):
        cs = CookieSession()
        cs.set("tok", "val", domain="example.com")
        hc = cs.to_httpx_cookies()
        assert isinstance(hc, httpx.Cookies)
        assert hc.get("tok") == "val"

    def test_expired_cookie_skipped(self):
        cs = CookieSession().from_json([{
            "name": "old", "value": "x", "domain": "e.com", "path": "/",
            "expires": 1000000,  # 1970s → expired
        }])
        hc = cs.to_httpx_cookies()
        assert hc.get("old") is None

    def test_update_from_httpx(self):
        cs = CookieSession()
        hc = httpx.Cookies()
        hc.set("new_cookie", "new_val", domain="site.com")
        cs.update_from_httpx(hc)
        assert cs.get("new_cookie") == "new_val"

    def test_template_cookie_access(self):
        """_cookies['name'] pattern used in original QD templates."""
        from qd_core.client.render import render_string

        cs = CookieSession()
        cs.set("csrf", "token99")
        assert render_string("{{ _cookies['csrf'] }}", {}, cookies=cs) == "token99"
