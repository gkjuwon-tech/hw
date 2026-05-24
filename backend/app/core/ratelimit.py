"""In-process token-bucket rate limiter.

A pragmatic single-process implementation: each bucket is keyed by API
key (preferred) or client IP (fallback). For multi-replica deployments,
swap the backing dict for Redis with the same interface — the call sites
do not change.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

from app.core.config import settings


@dataclass
class _Bucket:
    capacity: float
    refill_per_second: float
    tokens: float = field(init=False)
    updated_at: float = field(init=False)

    def __post_init__(self) -> None:
        self.tokens = self.capacity
        self.updated_at = time.monotonic()

    def take(self, cost: float = 1.0) -> bool:
        now = time.monotonic()
        delta = now - self.updated_at
        self.updated_at = now
        self.tokens = min(self.capacity, self.tokens + delta * self.refill_per_second)
        if self.tokens >= cost:
            self.tokens -= cost
            return True
        return False

    @property
    def retry_after(self) -> float:
        if self.refill_per_second <= 0:
            return 60.0
        missing = max(0.0, 1.0 - self.tokens)
        return missing / self.refill_per_second


class RateLimiter:
    """Per-key token-bucket limiter."""

    def __init__(self, default_per_minute: int, burst: int) -> None:
        self._default_per_minute = default_per_minute
        self._burst = burst
        self._buckets: dict[str, _Bucket] = {}
        self._overrides: dict[str, tuple[float, float]] = {}
        self._lock = asyncio.Lock()

    def set_override(self, key: str, per_minute: int) -> None:
        """Set a per-key rate (e.g. for an enterprise org). 0 clears."""
        if per_minute <= 0:
            self._overrides.pop(key, None)
            return
        refill = per_minute / 60.0
        capacity = max(float(self._burst), refill * 2.0)
        self._overrides[key] = (capacity, refill)

    async def check(self, key: str) -> tuple[bool, float]:
        """Returns ``(allowed, retry_after_seconds)``."""
        async with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                capacity, refill = self._overrides.get(
                    key, (float(self._burst), self._default_per_minute / 60.0)
                )
                bucket = _Bucket(capacity=capacity, refill_per_second=refill)
                self._buckets[key] = bucket
            ok = bucket.take()
            return ok, 0.0 if ok else bucket.retry_after


_limiter: RateLimiter | None = None


def get_limiter() -> RateLimiter:
    global _limiter
    if _limiter is None:
        _limiter = RateLimiter(
            default_per_minute=settings.rate_limit_default_per_minute,
            burst=settings.rate_limit_burst,
        )
    return _limiter


def reset_limiter() -> None:
    """Used in tests."""
    global _limiter
    _limiter = None
