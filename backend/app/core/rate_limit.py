"""In-memory rate limiting for the authentication endpoints.

Each key (e.g. ``login:ip:203.0.113.10``) keeps the times of its recent hits; a request is
refused while the key has used up its limit within the sliding window.

The counters live in the process. The production stack runs a single backend process, so
this is enough there; with several processes or hosts every process would count on its own
and the counters would have to move to PostgreSQL or Redis.
"""

from __future__ import annotations

import math
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from http import HTTPStatus

from app.core.exceptions import AppError


@dataclass(frozen=True, slots=True)
class Limit:
    attempts: int
    period: float  # seconds


# Every login attempt from one IP address (slows down password spraying).
LOGIN_PER_IP = Limit(30, 5 * 60)
# Failed logins for one email address; a successful login clears the counter.
LOGIN_FAILURES_PER_EMAIL = Limit(10, 15 * 60)
# New accounts from one IP address.
REGISTER_PER_IP = Limit(10, 60 * 60)
# Token refreshes from one IP address (generous: every open tab refreshes).
REFRESH_PER_IP = Limit(120, 5 * 60)
# Wrong current passwords when changing the password, per user.
PASSWORD_FAILURES_PER_USER = Limit(5, 15 * 60)


class TooManyRequestsError(AppError):
    status_code = HTTPStatus.TOO_MANY_REQUESTS
    code = "TOO_MANY_REQUESTS"
    message = "Too many attempts. Please wait and try again."

    def __init__(self, retry_after: int) -> None:
        super().__init__(
            details={"retry_after": retry_after}, headers={"Retry-After": str(retry_after)}
        )


class RateLimiter:
    def __init__(
        self,
        *,
        enabled: bool = True,
        clock: Callable[[], float] = time.monotonic,
        max_keys: int = 100_000,
    ) -> None:
        self.enabled = enabled
        self._clock = clock
        self._max_keys = max_keys
        # key -> (window length, hit times; at most `attempts` of them are kept)
        self._hits: dict[str, tuple[float, deque[float]]] = {}

    def _recent(self, key: str, now: float) -> deque[float] | None:
        entry = self._hits.get(key)
        if entry is None:
            return None
        period, hits = entry
        while hits and hits[0] <= now - period:
            hits.popleft()
        if not hits:
            del self._hits[key]
            return None
        return hits

    def check(self, key: str, limit: Limit) -> None:
        """Raise ``TooManyRequestsError`` when ``key`` has used up ``limit``."""
        if not self.enabled:
            return
        now = self._clock()
        hits = self._recent(key, now)
        if hits is not None and len(hits) >= limit.attempts:
            raise TooManyRequestsError(max(1, math.ceil(hits[0] + limit.period - now)))

    def hit(self, key: str, limit: Limit) -> None:
        """Record one attempt for ``key``."""
        if not self.enabled:
            return
        now = self._clock()
        hits = self._recent(key, now)
        if hits is None:
            if len(self._hits) >= self._max_keys:
                self._evict(now)
            hits = deque(maxlen=limit.attempts)
            self._hits[key] = (limit.period, hits)
        hits.append(now)

    def consume(self, key: str, limit: Limit) -> None:
        """``check`` and, when allowed, ``hit``: for limits on every attempt."""
        self.check(key, limit)
        self.hit(key, limit)

    def reset(self, key: str | None = None) -> None:
        """Forget one key, or everything."""
        if key is None:
            self._hits.clear()
        else:
            self._hits.pop(key, None)

    def _evict(self, now: float) -> None:
        for key in list(self._hits):
            self._recent(key, now)
        # Still full (a flood of distinct keys): drop the oldest entries.
        overflow = len(self._hits) - self._max_keys + 1
        for key in list(self._hits)[: max(overflow, 0)]:
            del self._hits[key]
