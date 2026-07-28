"""Tests for the QD v1 compatible rule engine (asserts + variable extraction)."""

import httpx

from qd_core.client.rule import run_rule
from qd_core.schemas.har import AssertRule, ExtractRule, RequestRule


def make_response(
    body: str = "",
    status_code: int = 200,
    headers: dict | None = None,
) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        headers=headers or {},
        text=body,
        request=httpx.Request("GET", "https://example.com/"),
    )


class TestSuccessAsserts:
    def test_no_rule_is_success(self):
        ok, msg = run_rule(make_response("anything"), None, {})
        assert ok and msg == ""

    def test_success_assert_match(self):
        rule = RequestRule(success_asserts=[AssertRule(re="签到成功", from_="content")])
        ok, msg = run_rule(make_response("恭喜，签到成功！"), rule, {})
        assert ok

    def test_success_assert_no_match(self):
        rule = RequestRule(success_asserts=[AssertRule(re="签到成功", from_="content")])
        ok, msg = run_rule(make_response("失败了"), rule, {})
        assert not ok
        assert "success_asserts" in msg

    def test_success_assert_on_status(self):
        rule = RequestRule(success_asserts=[AssertRule(re="200", from_="status")])
        ok, _ = run_rule(make_response("x", status_code=200), rule, {})
        assert ok

    def test_success_assert_multiple_any_match(self):
        rule = RequestRule(
            success_asserts=[
                AssertRule(re="不会匹配", from_="content"),
                AssertRule(re="successful", from_="content"),
            ]
        )
        ok, _ = run_rule(make_response("operation successful"), rule, {})
        assert ok


class TestFailedAsserts:
    def test_failed_assert_match_fails(self):
        rule = RequestRule(failed_asserts=[AssertRule(re="已经签到", from_="content")])
        ok, msg = run_rule(make_response("您今天已经签到过了"), rule, {})
        assert not ok
        assert "failed_asserts" in msg

    def test_failed_assert_no_match_ok(self):
        rule = RequestRule(failed_asserts=[AssertRule(re="已经签到", from_="content")])
        ok, _ = run_rule(make_response("签到成功"), rule, {})
        assert ok

    def test_header_source(self):
        rule = RequestRule(failed_asserts=[AssertRule(re="text/html", from_="header-Content-Type")])
        ok, _ = run_rule(make_response("x", headers={"Content-Type": "text/html"}), rule, {})
        assert not ok


class TestExtractVariables:
    def test_extract_simple(self):
        rule = RequestRule(extract_variables=[ExtractRule(name="token", re='"token":"([^"]+)"', from_="content")])
        variables = {}
        run_rule(make_response('{"token":"abc123"}'), rule, variables)
        assert variables["token"] == "abc123"

    def test_extract_group0_when_no_groups(self):
        rule = RequestRule(extract_variables=[ExtractRule(name="num", re=r"\d+", from_="content")])
        variables = {}
        run_rule(make_response("id=42"), rule, variables)
        assert variables["num"] == "42"

    def test_extract_findall_with_g_flag(self):
        rule = RequestRule(extract_variables=[ExtractRule(name="all_nums", re=r"/(\d+)/g", from_="content")])
        variables = {}
        run_rule(make_response("a1 b22 c333"), rule, variables)
        assert variables["all_nums"] == ["1", "22", "333"]

    def test_extract_ignorecase_flag(self):
        rule = RequestRule(extract_variables=[ExtractRule(name="word", re="/HELLO/i", from_="content")])
        variables = {}
        run_rule(make_response("say hello there"), rule, variables)
        assert variables["word"] == "hello"

    def test_extract_from_header(self):
        rule = RequestRule(extract_variables=[ExtractRule(name="session", re="sid=([a-z0-9]+)", from_="header-Set-Cookie")])
        variables = {}
        run_rule(make_response("x", headers={"Set-Cookie": "sid=deadbeef; Path=/"}), rule, variables)
        assert variables["session"] == "deadbeef"

    def test_assert_pattern_with_jinja_var(self):
        rule = RequestRule(success_asserts=[AssertRule(re="{{expected}}", from_="content")])
        ok, _ = run_rule(make_response("hello world"), rule, {"expected": "world"})
        assert ok
