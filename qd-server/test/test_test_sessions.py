"""Tests for short-lived template-editor request sessions."""

import time

from qd_server.services import test_sessions


def test_session_store_expires_idle_state(monkeypatch):
    monkeypatch.setattr(test_sessions, "TEST_SESSION_TTL_SECONDS", 10)
    store = test_sessions.TestSessionStore()
    expired = store.get(1, "flow")
    expired.last_used_at = time.monotonic() - 11

    replacement = store.get(1, "flow")

    assert replacement is not expired


def test_session_store_evicts_oldest_state(monkeypatch):
    monkeypatch.setattr(test_sessions, "MAX_TEST_SESSIONS", 2)
    store = test_sessions.TestSessionStore()
    oldest = store.get(1, "oldest")
    oldest.last_used_at = 1
    store.get(1, "newer")

    store.get(1, "newest")

    assert (1, "oldest") not in store._sessions
    assert (1, "newer") in store._sessions
    assert (1, "newest") in store._sessions


def test_session_store_clear_is_scoped_to_user():
    store = test_sessions.TestSessionStore()
    store.get(1, "shared")
    other_user_state = store.get(2, "shared")

    store.clear(1, "shared")

    assert (1, "shared") not in store._sessions
    assert store.get(2, "shared") is other_user_state
