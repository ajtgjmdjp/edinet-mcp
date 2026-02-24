"""Tests for edinet_mcp._rate_limiter."""

from __future__ import annotations

import time

import pytest

from edinet_mcp._rate_limiter import RateLimiter


class TestRateLimiter:
    def test_default_rate(self) -> None:
        limiter = RateLimiter()
        # Default rate=0.5 → min_interval=2.0
        assert limiter._min_interval == pytest.approx(2.0)

    def test_custom_rate(self) -> None:
        limiter = RateLimiter(rate=10.0)
        assert limiter._min_interval == pytest.approx(0.1)

    @pytest.mark.asyncio
    async def test_consecutive_waits_respect_interval(self) -> None:
        limiter = RateLimiter(rate=20.0)  # min_interval=0.05s
        min_interval = limiter._min_interval

        await limiter.wait()
        start = time.monotonic()
        await limiter.wait()
        elapsed = time.monotonic() - start

        assert elapsed >= min_interval * 0.9  # small tolerance for timing

    @pytest.mark.asyncio
    async def test_rate_zero_no_sleep(self) -> None:
        limiter = RateLimiter(rate=0)
        assert limiter._min_interval == 0.0

        start = time.monotonic()
        await limiter.wait()
        await limiter.wait()
        elapsed = time.monotonic() - start

        # Should be essentially instant (< 10ms)
        assert elapsed < 0.01
