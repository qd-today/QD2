"""Security-sensitive configuration and request schema tests."""

import pytest
from pydantic import ValidationError
from qd_core.plugins.manager import QDPluginManager
from qd_server.api.auth import RegisterRequest
from qd_server.api.test_request import TestRequest as RequestUnderTest
from qd_server.config import (
    DEFAULT_ENCRYPTION_KEY,
    DEFAULT_JWT_SECRET,
    QDServerSettings,
    ensure_encryption_key,
    ensure_jwt_secret,
)


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


def test_priority_environment_settings_are_applied(monkeypatch):
    monkeypatch.setenv("QD_TASK_REQUEST_LIMIT", "321")
    monkeypatch.setenv("QD_TASK_TIMEOUT", "45")
    monkeypatch.setenv("QD_WHILE_LOOP_LIMIT", "77")
    monkeypatch.setenv("QD_WHILE_LOOP_TIMEOUT", "12.5")
    monkeypatch.setenv("QD_LOGIN_RATE_LIMIT", "4")
    monkeypatch.setenv("QD_PUBLIC_URL", "https://qd.example.test/")
    monkeypatch.setenv("QD_SMTP_SSL", "true")
    monkeypatch.setenv("QD_SMTP_STARTTLS", "false")
    monkeypatch.setenv("QD_WS_MAX_QUEUE_SIZE", "42")

    settings = QDServerSettings(_env_file=None)

    assert settings.task_request_limit == 321
    assert settings.task_timeout == 45
    assert settings.while_loop_limit == 77
    assert settings.while_loop_timeout == 12.5
    assert settings.login_rate_limit == 4
    assert settings.public_url == "https://qd.example.test"
    assert settings.smtp.ssl is True
    assert settings.smtp.starttls is False
    assert settings.ws_max_queue_size == 42


def test_encryption_key_uses_fixed_default_and_allows_override(tmp_path):
    settings = QDServerSettings(config_dir=tmp_path)
    ensure_encryption_key(settings)
    assert settings.encryption_key == DEFAULT_ENCRYPTION_KEY
    assert not (tmp_path / "encryption-key").exists()

    custom = QDServerSettings(config_dir=tmp_path, encryption_key="custom-key")
    ensure_encryption_key(custom)
    assert custom.encryption_key == "custom-key"


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
