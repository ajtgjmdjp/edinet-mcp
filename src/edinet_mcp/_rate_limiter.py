"""Async token-bucket rate limiter for EDINET API compliance."""

from __future__ import annotations

import asyncio
import time


class RateLimiter:
    """Simple token-bucket rate limiter.

    Ensures we don't exceed a given number of requests per second
    against the EDINET API.

    Args:
        rate: Maximum requests per second.
    """

    def __init__(self, rate: float = 0.5) -> None:
        self._min_interval = 1.0 / rate if rate > 0 else 0.0
        self._last_request: float = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        """Await until the next request is allowed."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_request
            if elapsed < self._min_interval:
                await asyncio.sleep(self._min_interval - elapsed)
            self._last_request = time.monotonic()
