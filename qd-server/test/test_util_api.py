"""Regression tests for QD v1-compatible public utility routes."""

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from qd_server.api import test_request, util
from qd_server.middleware.auth import get_current_user
from qd_server.models.user import User


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(util.router, prefix="/util")
    app.include_router(test_request.router, prefix="/api/test")
    app.dependency_overrides[get_current_user] = lambda: User(
        id=1,
        username="util-test",
        hashed_password="x",
    )
    return TestClient(app)


def test_timestamp_and_encoding_routes(client):
    timestamp = client.get("/util/timestamp", params={"ts": "0"})
    assert timestamp.status_code == 200
    assert timestamp.json()["时间戳"] == 0
    assert timestamp.json()["状态"] == "200"

    unicode_response = client.get("/util/unicode", params={"content": r"\u4f60\u597d"})
    assert unicode_response.json() == {"转换后": "你好", "状态": "200"}

    gb2312 = client.get("/util/gb2312", params={"content": "中文"})
    assert gb2312.json() == {"转换后": "%D6%D0%CE%C4", "状态": "200"}


def test_regex_and_string_replace_routes(client):
    regex_response = client.post(
        "/util/regex",
        data={"data": "A1 b2", "p": r"([a-z])(\d)"},
    )
    assert regex_response.json() == {
        "数据": {"1": ["A", "1"], "2": ["b", "2"]},
        "状态": "OK",
    }

    replace_response = client.get(
        "/util/string/replace",
        params={"s": "a-1", "p": r"\d", "t": "x", "r": "text"},
    )
    assert replace_response.text == "a-x"


@pytest.mark.asyncio
async def test_delay_clamps_and_rejects_non_finite(monkeypatch):
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(util.asyncio, "sleep", fake_sleep)
    response = await util._do_delay("31")
    assert sleeps == [30]
    assert "limited" in response.body.decode()

    response = await util._do_delay("nan")
    assert sleeps == [30]
    assert response.body.decode() == "Error, delay 0.0 second."


def test_public_input_limits_are_enforced():
    with pytest.raises(HTTPException) as error:
        util._regex_findall("x", "a" * (util.MAX_PATTERN_LENGTH + 1))
    assert error.value.status_code == 413


def test_request_api_supports_qd_internal_scheme(client):
    response = client.post(
        "/api/test/test",
        json={"method": "GET", "url": "api://util/delay/0"},
    )

    assert response.status_code == 200
    assert response.json()["status_code"] == 200
    assert response.json()["error"] is None
    assert response.json()["body"] == "delay 0.0 second."


def test_request_api_reports_unsupported_internal_service(client):
    response = client.post(
        "/api/test/test",
        json={"method": "GET", "url": "api://admin/users"},
    )

    assert response.status_code == 200
    assert response.json()["status_code"] == 0
    assert "Unsupported api:// service" in response.json()["error"]


def test_request_api_reports_unsupported_util_path(client):
    response = client.post(
        "/api/test/test",
        json={"method": "GET", "url": "api://util/not-migrated"},
    )

    assert response.status_code == 200
    assert response.json()["status_code"] == 0
    assert "Unsupported api://util path" in response.json()["error"]
