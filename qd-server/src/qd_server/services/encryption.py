"""Authenticated encryption for sensitive JSON database fields."""

import base64
import binascii
import hashlib
import json
from functools import lru_cache
from typing import Any

from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
from sqlmodel import select

from qd_server.config import QDServerSettings, ensure_encryption_key, get_settings

WRAPPER_KEY = "__qd2_encrypted__"
TOKEN_PREFIX = "qd2:v1"


class DataDecryptionError(RuntimeError):
    """Raised when stored data cannot be decrypted by any configured key."""


class DataCipher:
    def __init__(self, current_key: str):
        self._keys = {
            self._key_id(current_key): hashlib.sha256(current_key.encode("utf-8")).digest()
        }
        self.current_key_id = self._key_id(current_key)

    @staticmethod
    def _key_id(key: str) -> str:
        return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _aad(purpose: str) -> bytes:
        return f"{TOKEN_PREFIX}:{purpose}".encode()

    def encrypt(self, value: Any, purpose: str) -> str:
        nonce = get_random_bytes(12)
        cipher = AES.new(self._keys[self.current_key_id], AES.MODE_GCM, nonce=nonce)
        cipher.update(self._aad(purpose))
        plaintext = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ciphertext, tag = cipher.encrypt_and_digest(plaintext)
        payload = base64.urlsafe_b64encode(nonce + tag + ciphertext).decode("ascii")
        return f"{TOKEN_PREFIX}:{self.current_key_id}:{payload}"

    def decrypt(self, token: str, purpose: str) -> Any:
        try:
            prefix, version, key_id, payload = token.split(":", 3)
            if f"{prefix}:{version}" != TOKEN_PREFIX:
                raise ValueError("unsupported token version")
            key = self._keys[key_id]
            packed = base64.urlsafe_b64decode(payload.encode("ascii"))
            nonce, tag, ciphertext = packed[:12], packed[12:28], packed[28:]
            cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
            cipher.update(self._aad(purpose))
            plaintext = cipher.decrypt_and_verify(ciphertext, tag)
            return json.loads(plaintext.decode("utf-8"))
        except (KeyError, ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError, binascii.Error) as exc:
            raise DataDecryptionError(
                f"Unable to decrypt {purpose}; QD_ENCRYPTION_KEY is incorrect"
            ) from exc

    def uses_current_key(self, token: str) -> bool:
        return token.startswith(f"{TOKEN_PREFIX}:{self.current_key_id}:")


@lru_cache
def get_data_cipher() -> DataCipher:
    settings = get_settings()
    ensure_encryption_key(settings)
    return DataCipher(settings.encryption_key)


def protect_dict(value: dict | None, purpose: str) -> dict:
    value = dict(value or {})
    if not value:
        return {}
    return {WRAPPER_KEY: get_data_cipher().encrypt(value, purpose)}


def unprotect_dict(value: dict | None, purpose: str) -> dict:
    value = dict(value or {})
    token = value.get(WRAPPER_KEY)
    if token is None:
        return value
    decoded = get_data_cipher().decrypt(token, purpose)
    if not isinstance(decoded, dict):
        raise DataDecryptionError(f"Decrypted {purpose} value is not an object")
    return decoded


def protect_list(value: list | None, purpose: str) -> list:
    value = list(value or [])
    if not value:
        return []
    return [{WRAPPER_KEY: get_data_cipher().encrypt(value, purpose)}]


def unprotect_list(value: list | None, purpose: str) -> list:
    value = list(value or [])
    if len(value) != 1 or not isinstance(value[0], dict) or WRAPPER_KEY not in value[0]:
        return value
    decoded = get_data_cipher().decrypt(value[0][WRAPPER_KEY], purpose)
    if not isinstance(decoded, list):
        raise DataDecryptionError(f"Decrypted {purpose} value is not a list")
    return decoded


def _needs_protection(value: dict | list | None) -> bool:
    if not value:
        return False
    wrapper = value if isinstance(value, dict) else value[0] if len(value) == 1 else None
    if not isinstance(wrapper, dict) or WRAPPER_KEY not in wrapper:
        return True
    return not get_data_cipher().uses_current_key(wrapper[WRAPPER_KEY])


async def migrate_sensitive_storage(settings: QDServerSettings) -> int:
    """Encrypt legacy plaintext and rotate values encrypted with previous keys."""
    from qd_server.models.notification import Notification
    from qd_server.models.task import Task

    changed = 0
    async with settings.db.scoped_session() as session:
        tasks = (await session.execute(select(Task))).scalars().all()
        for task in tasks:
            if _needs_protection(task.variables):
                task.variables = protect_dict(unprotect_dict(task.variables, "task.variables"), "task.variables")
                changed += 1
            if _needs_protection(task.cookie_session):
                task.cookie_session = protect_list(
                    unprotect_list(task.cookie_session, "task.cookie_session"),
                    "task.cookie_session",
                )
                changed += 1
            session.add(task)

        notifications = (await session.execute(select(Notification))).scalars().all()
        for notification in notifications:
            if _needs_protection(notification.config):
                notification.config = protect_dict(
                    unprotect_dict(notification.config, "notification.config"),
                    "notification.config",
                )
                changed += 1
                session.add(notification)
        if changed:
            await session.commit()
    return changed
