"""Enterprise WeChat application notification tests."""

import pytest

from qd_server.api.notifications import CHANNEL_SCHEMAS
from qd_server.services import notification


class FakeResponse:
    def __init__(self, data: dict, status_code: int = 200):
        self._data = data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise notification.httpx.HTTPStatusError(
                "request failed", request=None, response=None
            )

    def json(self):
        return self._data


class FakeClient:
    token_data = {"errcode": 0, "access_token": "access-secret"}
    send_data = {"errcode": 0, "errmsg": "ok"}
    calls: list[tuple[str, str, dict]] = []

    def __init__(self, **_kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def get(self, url: str, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return FakeResponse(self.token_data)

    async def post(self, url: str, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return FakeResponse(self.send_data)


@pytest.fixture(autouse=True)
def fake_http_client(monkeypatch):
    FakeClient.calls = []
    FakeClient.token_data = {"errcode": 0, "access_token": "access-secret"}
    FakeClient.send_data = {"errcode": 0, "errmsg": "ok"}
    monkeypatch.setattr(notification.httpx, "AsyncClient", FakeClient)


@pytest.mark.asyncio
async def test_wecom_app_gets_token_and_sends_message():
    ok = await notification.send_notification(
        {
            "type": "wecom_app",
            "corp_id": "corp-id",
            "corp_secret": "corp-secret",
            "agent_id": "1000002",
            "touser": "user1|user2",
        },
        task_name="签到",
        status="success",
        duration_seconds=1.5,
        task_log="签到成功",
    )

    assert ok is True
    assert len(FakeClient.calls) == 2
    method, url, kwargs = FakeClient.calls[0]
    assert method == "GET"
    assert url.endswith("/cgi-bin/gettoken")
    assert kwargs["params"] == {"corpid": "corp-id", "corpsecret": "corp-secret"}

    method, url, kwargs = FakeClient.calls[1]
    assert method == "POST"
    assert url.endswith("/cgi-bin/message/send")
    assert kwargs["params"] == {"access_token": "access-secret"}
    assert kwargs["json"]["agentid"] == 1000002
    assert kwargs["json"]["touser"] == "user1|user2"
    content = kwargs["json"]["text"]["content"]
    assert "签到" in content
    assert "日志: 签到成功" in content
    assert "耗时" not in content


@pytest.mark.asyncio
async def test_wecom_app_accepts_original_qd_field_aliases():
    ok = await notification.send_wecom_app(
        {"corpid": "corp", "corpsecret": "secret", "agentid": 9, "touser": "@all"},
        task_name="test",
        status="failed",
    )

    assert ok is True
    assert FakeClient.calls[1][2]["json"]["agentid"] == 9


@pytest.mark.asyncio
async def test_wecom_app_rejects_token_api_error():
    FakeClient.token_data = {"errcode": 40013, "errmsg": "invalid corpid"}

    ok = await notification.send_wecom_app(
        {"corp_id": "bad", "corp_secret": "secret", "agent_id": 1, "touser": "u"},
        task_name="test",
        status="failed",
    )

    assert ok is False
    assert len(FakeClient.calls) == 1


@pytest.mark.asyncio
async def test_wecom_app_rejects_missing_or_invalid_config():
    assert await notification.send_wecom_app({}, "test", "failed") is False
    assert (
        await notification.send_wecom_app(
            {"corp_id": "c", "corp_secret": "s", "agent_id": "bad", "touser": "u"},
            "test",
            "failed",
        )
        is False
    )
    assert FakeClient.calls == []


def test_wecom_app_channel_metadata():
    assert CHANNEL_SCHEMAS["wecom_app"] == {
        "label": "企业微信 Pusher",
        "fields": ["corp_id", "corp_secret", "agent_id", "touser"],
    }
