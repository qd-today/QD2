"""Short-lived execution state for template-editor request tests."""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from qd_core.client.cookie_session import CookieSession

TEST_SESSION_TTL_SECONDS = 30 * 60
MAX_TEST_SESSIONS = 1_000


@dataclass
class TestSessionState:
    cookies: CookieSession = field(default_factory=CookieSession)
    variables: dict[str, Any] = field(default_factory=dict)
    last_used_at: float = field(default_factory=time.monotonic)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class TestSessionStore:
    def __init__(self) -> None:
        self._sessions: dict[tuple[int, str], TestSessionState] = {}

    def get(self, user_id: int, session_id: str) -> TestSessionState:
        now = time.monotonic()
        self._remove_expired(now)
        key = (user_id, session_id)
        state = self._sessions.get(key)
        if state is None:
            self._evict_oldest_if_full()
            state = TestSessionState(last_used_at=now)
            self._sessions[key] = state
        state.last_used_at = now
        return state

    def clear(self, user_id: int, session_id: str) -> None:
        self._sessions.pop((user_id, session_id), None)

    def _remove_expired(self, now: float) -> None:
        expired = [
            key
            for key, state in self._sessions.items()
            if now - state.last_used_at > TEST_SESSION_TTL_SECONDS
        ]
        for key in expired:
            self._sessions.pop(key, None)

    def _evict_oldest_if_full(self) -> None:
        if len(self._sessions) < MAX_TEST_SESSIONS:
            return
        oldest_key = min(self._sessions, key=lambda key: self._sessions[key].last_used_at)
        self._sessions.pop(oldest_key, None)


test_session_store = TestSessionStore()
