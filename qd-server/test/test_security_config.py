"""Security-sensitive configuration and request schema tests."""

import pytest
from pydantic import ValidationError

from qd_core.plugins.manager import QDPluginManager
from qd_server.api.auth import RegisterRequest
from qd_server.api.test_request import TestRequest as RequestUnderTest
from qd_server.config import DEFAULT_JWT_SECRET, QDServerSettings, ensure_jwt_secret


def test_default_jwt_secret_is_generated_once(tmp_path):
    first = QDServerSettings(config_dir=tmp_path)
    assert first.jwt.secret_key == DEFAULT_JWT_SECRET
    ensure_jwt_secret(first)
    generated = first.jwt.secret_key
    assert generated != DEFAULT_JWT_SECRET
    assert len(generated) >= 32

    second = QDServerSettings(config_dir=tmp_path)
    ensure_jwt_secret(second)
    assert second.jwt.secret_key == generated


def test_nested_environment_settings_are_applied(monkeypatch, tmp_path):
    database_path = tmp_path / "from-environment.db"
    monkeypatch.setenv("QD_DB__DB_TYPE", "sqlite3")
    monkeypatch.setenv("QD_DB__ENGINE_SETTINGS__DB_PATH", str(database_path))

    settings = QDServerSettings()

    assert settings.db.db_type.value == "sqlite3"
    assert settings.db.engine_settings.db_path == database_path


def test_auth_and_test_request_bounds():
    with pytest.raises(ValidationError):
        RegisterRequest(username="   ", password="123456")
    with pytest.raises(ValidationError):
        RegisterRequest(username="user", password="123")
    with pytest.raises(ValidationError):
        RequestUnderTest(url="https://example.test", timeout=0)
    assert RequestUnderTest(url="https://example.test").verify_tls is True


def test_plugin_manager_module_and_listing_load():
    manager = QDPluginManager("qd.plugins")
    assert isinstance(manager.list_plugins(), dict)
