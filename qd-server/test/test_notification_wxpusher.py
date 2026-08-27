"""Wxpusher notification compatibility tests."""

import pytest
from qd_server.api.notifications import CHANNEL_SCHEMAS
from qd_server.services import notification


class FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {"code": 1000}


class FakeClient:
    request_json = None

    def __init__(self, **_kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def post(self, _url, json):
        FakeClient.request_json = json
        return FakeResponse()


@pytest.mark.asyncio
async def test_wxpusher_channel_sends_migrated_config(monkeypatch):
    monkeypatch.setattr(notification.httpx, "AsyncClient", FakeClient)

    assert CHANNEL_SCHEMAS["wxpusher"]["fields"] == ["app_token", "uids"]
    assert await notification.send_notification(
        {
            "type": "wxpusher",
            "app_token": "AT_test",
            "uids": "UID_one, UID_two",
        },
        task_name="migration",
        status="success",
    )
    assert FakeClient.request_json["appToken"] == "AT_test"
    assert FakeClient.request_json["uids"] == ["UID_one", "UID_two"]
