"""Token-bucket limiter unit tests."""

from __future__ import annotations

import asyncio

import pytest

from app.core.ratelimit import RateLimiter


async def test_burst_then_blocks() -> None:
    limiter = RateLimiter(default_per_minute=60, burst=3)
    # First three requests succeed within the burst window.
    for _ in range(3):
        ok, retry = await limiter.check("k")
        assert ok
        assert retry == 0.0
    # The 4th is rejected.
    ok, retry = await limiter.check("k")
    assert ok is False
    assert retry > 0


async def test_per_key_independent() -> None:
    limiter = RateLimiter(default_per_minute=60, burst=1)
    ok, _ = await limiter.check("a")
    assert ok
    ok, _ = await limiter.check("a")
    assert ok is False
    # Different key — independent bucket.
    ok, _ = await limiter.check("b")
    assert ok


async def test_override_raises_capacity() -> None:
    limiter = RateLimiter(default_per_minute=60, burst=1)
    limiter.set_override("k", per_minute=600)  # 10/s, capacity 20
    for _ in range(10):
        ok, _ = await limiter.check("k")
        assert ok


@pytest.mark.asyncio
async def test_refill_eventually_allows() -> None:
    limiter = RateLimiter(default_per_minute=60_000, burst=1)  # 1000 req/s, refill fast
    ok, _ = await limiter.check("k")
    assert ok
    ok, _ = await limiter.check("k")
    # Burst exhausted — but refill is sub-ms.
    await asyncio.sleep(0.02)
    ok, _ = await limiter.check("k")
    assert ok
