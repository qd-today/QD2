"""Sensitive storage encryption and failed-login limiter tests."""

import pytest
import qd_server.services.encryption as encryption
import qd_server.services.login_limiter as limiter_module
from qd_server.services.encryption import DataCipher, DataDecryptionError
from qd_server.services.login_limiter import LoginRateLimiter


def test_sensitive_json_roundtrip_does_not_store_plaintext(monkeypatch):
    cipher = DataCipher("current-key-with-at-least-32-characters")
    monkeypatch.setattr(encryption, "get_data_cipher", lambda: cipher)

    protected = encryption.protect_dict({"password": "secret-value"}, "task.variables")

    assert "secret-value" not in str(protected)
    assert encryption.unprotect_dict(protected, "task.variables") == {"password": "secret-value"}


def test_wrong_key_cannot_decrypt_sensitive_data():
    current_cipher = DataCipher("current-key")
    token = current_cipher.encrypt([{"name": "session", "value": "abc"}], "task.cookie_session")

    with pytest.raises(DataDecryptionError):
        DataCipher("different-key").decrypt(token, "task.cookie_session")


def test_login_limiter_expires_and_clears(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(limiter_module.time, "monotonic", lambda: now[0])
    limiter = LoginRateLimiter()

    limiter.record_failure("client-user", 60)
    limiter.record_failure("client-user", 60)
    assert limiter.retry_after("client-user", 2, 60) == 60

    limiter.clear("client-user")
    assert limiter.retry_after("client-user", 2, 60) == 0

    limiter.record_failure("client-user", 60)
    now[0] = 161.0
    assert limiter.retry_after("client-user", 2, 60) == 0
