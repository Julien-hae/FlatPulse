"""Rate limiter implementation using token buckets."""

import asyncio
import time


class RateLimiter:
    """Rate limiter that uses token buckets for each slug."""

    def __init__(self, rpm_by_slug: dict[str, int]):
        """Initialize the rate limiter with the given rate limits by slug.

        Args:
            rpm_by_slug (dict[str, int]): A dictionary mapping slugs to their rate limits per minute.
        """
        self.rpm_by_slug = rpm_by_slug
        self._buckets = {}
        for key, val in rpm_by_slug.items():
            self._buckets[key] = TokenBucket(rpm=val)

    async def acquire(self, slug: str) -> None:
        """Acquire a token from the rate limiter for the given slug."""
        bucket = self._buckets[slug]
        delay = bucket.try_acquire()
        while delay > 0.0:
            await asyncio.sleep(delay)
            delay = bucket.try_acquire()

    def can_acquire(self, slug: str) -> bool:
        """Check if a token can be acquired for the given slug."""
        return self._buckets[slug].can_acquire()


class TokenBucket:
    """Token bucket implementation for rate limiting."""

    def __init__(self, rpm: int) -> None:
        """Initialize the token bucket with the given rate per minute.

        Args:
            rpm (int): The rate per minute for the token bucket.
        """
        self._capacity = float(rpm)
        self._rate = rpm / 60.0
        self._tokens = float(rpm)
        self._last = time.monotonic()

    def _refill(self) -> None:
        """Refill the token bucket based on the elapsed time."""
        now = time.monotonic()
        self._tokens = min(
            self._capacity, self._tokens + (now - self._last) * self._rate
        )
        self._last = now

    def can_acquire(self) -> bool:
        """Check if a token can be acquired from the bucket."""
        self._refill()
        return self._tokens >= 1

    def try_acquire(self) -> float:
        """Return 0.0 if a token was acquired, otherwise return the wait time in seconds."""
        self._refill()
        if self._tokens >= 1:
            self._tokens -= 1
            return 0.0
        return (1 - self._tokens) / self._rate
