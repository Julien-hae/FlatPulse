"""Rate limiter implementation using token buckets."""

import asyncio
import time
from collections.abc import Mapping


class RateLimiter:
    """Rate limiter that spaces requests using one-token buckets for each slug."""

    def __init__(self, rpm_by_slug: Mapping[str, int]) -> None:
        """Give each slug its own bucket, refilled at its rate per minute.

        Raises:
            ValueError: A rate is zero or negative.
        """
        self._buckets = {slug: TokenBucket(rpm) for slug, rpm in rpm_by_slug.items()}

    async def acquire(self, slug: str) -> None:
        """Wait until the bucket of `slug` grants a token, and take it.

        Raises:
            KeyError: `slug` has no bucket.
        """
        bucket = self._bucket(slug)
        delay = bucket.try_acquire()
        while delay > 0.0:
            await asyncio.sleep(delay)
            delay = bucket.try_acquire()

    def can_acquire(self, slug: str) -> bool:
        """Whether the bucket of `slug` holds a token, without taking it.

        Raises:
            KeyError: `slug` has no bucket.
        """
        return self._bucket(slug).can_acquire()

    def _bucket(self, slug: str) -> TokenBucket:
        """The bucket of `slug`; an unknown slug is an error, never an unlimited rate."""
        if slug not in self._buckets:
            raise KeyError(f"Slug '{slug}' is not configured in the rate limiter.")
        return self._buckets[slug]


class TokenBucket:
    """One-token bucket enforcing a minimum interval of 60 / rpm seconds."""

    def __init__(self, rpm: int) -> None:
        """Start with one token, refilled at `rpm` tokens per minute.

        Raises:
            ValueError: `rpm` is zero or negative. A negative rate would compute
                negative waits, which `RateLimiter.acquire` reads as "no wait".
        """
        if rpm <= 0:
            raise ValueError(
                f"Rate per minute (rpm) must be greater than 0, got {rpm}."
            )
        self._capacity = 1.0
        self._rate = rpm / 60.0
        self._tokens = 1.0
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
