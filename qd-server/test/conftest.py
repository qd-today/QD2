"""Shared isolation fixtures for qd-server tests."""

import pytest
import qd_server.services.encryption as encryption
from qd_server.services.encryption import DataCipher


@pytest.fixture(autouse=True)
def isolated_data_encryption(monkeypatch):
    cipher = DataCipher("test-encryption-key-with-at-least-32-characters")
    monkeypatch.setattr(encryption, "get_data_cipher", lambda: cipher)
