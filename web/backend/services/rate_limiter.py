"""Thread-safe sliding-window rate limiter keyed by client identifier."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable

from web.backend.constants import (
    DEFAULT_NLP_RATE_LIMIT_PER_MINUTE,
    RATE_LIMIT_WINDOW_SECONDS,
)
from web.backend.exceptions import RateLimitError


class SlidingWindowRateLimiter:
    """In-memory sliding-window rate limiter per client key."""

    def __init__(
        self,
        max_requests: int = DEFAULT_NLP_RATE_LIMIT_PER_MINUTE,
        window_seconds: int = RATE_LIMIT_WINDOW_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Initialize sliding-window rate limiter bounds and clock."""
        self._max_requests = max_requests
        self._window_seconds = float(window_seconds)
        self._clock = clock
        self._lock = threading.Lock()
        self._requests: dict[str, deque[float]] = defaultdict(deque)

    def check_and_record(self, client_key: str) -> None:
        """Record a request for client_key or raise RateLimitError if exceeded."""
        now = self._clock()
        cutoff = now - self._window_seconds
        with self._lock:
            timestamps = self._requests[client_key]
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()
            if len(timestamps) >= self._max_requests:
                raise RateLimitError(
                    "Natural-language search rate limit exceeded",
                    details=(
                        f"Maximum {self._max_requests} requests per "
                        f"{int(self._window_seconds)} seconds allowed"
                    ),
                )
            timestamps.append(now)

    def reset(self) -> None:
        """Clear all tracked client request timestamps."""
        with self._lock:
            self._requests.clear()
