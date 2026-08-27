"""In-process failed-login rate limiting."""

import threading
import time
from collections import deque


class LoginRateLimiter:
    MAX_TRACKED_KEYS = 10_000

    def __init__(self) -> None:
        self._attempts: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _trim(attempts: deque[float], cutoff: float) -> None:
        while attempts and attempts[0] <= cutoff:
            attempts.popleft()

    def retry_after(self, key: str, limit: int, window_seconds: int) -> int:
        if limit == 0:
            return 0
        now = time.monotonic()
        with self._lock:
            attempts = self._attempts.get(key)
            if not attempts:
                return 0
            self._trim(attempts, now - window_seconds)
            if not attempts:
                self._attempts.pop(key, None)
                return 0
            if len(attempts) < limit:
                return 0
            return max(1, int(window_seconds - (now - attempts[0])))

    def record_failure(self, key: str, window_seconds: int) -> None:
        now = time.monotonic()
        with self._lock:
            if key not in self._attempts and len(self._attempts) >= self.MAX_TRACKED_KEYS:
                oldest_key = min(self._attempts, key=lambda item: self._attempts[item][-1])
                self._attempts.pop(oldest_key, None)
            attempts = self._attempts.setdefault(key, deque())
            self._trim(attempts, now - window_seconds)
            attempts.append(now)

    def clear(self, key: str) -> None:
        with self._lock:
            self._attempts.pop(key, None)


login_rate_limiter = LoginRateLimiter()
