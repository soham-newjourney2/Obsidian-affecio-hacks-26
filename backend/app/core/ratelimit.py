"""In-memory sliding-window rate limiter (single process, MVP)."""

import math
import time
from collections import defaultdict, deque
from collections.abc import Callable

from backend.app.core.errors import AppError


class RateLimiter:
    def __init__(
        self, limit: int, window_s: float, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.limit = limit
        self.window_s = window_s
        self._clock = clock
        self._hits: defaultdict[str, deque[float]] = defaultdict(deque)

    def hit(self, key: str) -> float | None:
        """Records a hit. Returns None if allowed, else seconds until the next slot frees."""
        now = self._clock()
        hits = self._hits[key]
        while hits and hits[0] <= now - self.window_s:
            hits.popleft()
        if len(hits) >= self.limit:
            return hits[0] + self.window_s - now
        hits.append(now)
        return None

    def check(self, key: str) -> None:
        retry_after = self.hit(key)
        if retry_after is not None:
            raise AppError(
                429,
                "RATE_LIMITED",
                "Too many attempts. Please wait and try again.",
                headers={"Retry-After": str(max(1, math.ceil(retry_after)))},
            )


class TokenBucket:
    """Per-key token bucket: `rate` tokens per second, up to `burst` saved (chat: 1/s, burst 5)."""

    def __init__(
        self, rate: float, burst: int, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.rate = rate
        self.burst = burst
        self._clock = clock
        self._state: dict[str, tuple[float, float]] = {}  # key -> (tokens, updated_at)

    def take(self, key: str) -> bool:
        now = self._clock()
        tokens, updated = self._state.get(key, (float(self.burst), now))
        tokens = min(self.burst, tokens + (now - updated) * self.rate)
        if tokens < 1:
            self._state[key] = (tokens, now)
            return False
        self._state[key] = (tokens - 1, now)
        return True

    def forget(self, key: str) -> None:
        self._state.pop(key, None)
