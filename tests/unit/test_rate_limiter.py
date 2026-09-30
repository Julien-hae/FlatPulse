"""Unit tests for the RateLimiter class."""

import unittest
from unittest.mock import patch

from flatpulse.scrapers.rate_limiter import RateLimiter


class TestRateLimiter(unittest.IsolatedAsyncioTestCase):
    """Unit tests for the RateLimiter class."""

    async def test_acquire_within_limit(self) -> None:
        """Test acquiring tokens within the rate limit."""
        limiter = RateLimiter({"naef": 10})
        for _ in range(10):
            await limiter.acquire("naef")

    async def test_acquire_blocks_over_limit(self) -> None:
        """Test that acquiring tokens blocks when over the rate limit."""
        with patch("flatpulse.scrapers.rate_limiter.time.monotonic") as fake_clock:
            fake_clock.return_value = 1000.0
            limiter = RateLimiter({"naef": 5})
            self.assertTrue(limiter.can_acquire("naef"))
            for _ in range(5):
                await limiter.acquire("naef")
            self.assertFalse(limiter.can_acquire("naef"))

    async def test_tokens_refill_over_time(self) -> None:
        """Test that tokens are refilled over time."""
        with patch("flatpulse.scrapers.rate_limiter.time.monotonic") as fake_clock:
            fake_clock.return_value = 1000.0
            limiter = RateLimiter({"naef": 5})
            for _ in range(5):
                await limiter.acquire("naef")
            self.assertFalse(limiter.can_acquire("naef"))

            fake_clock.return_value += 24
            self.assertTrue(limiter.can_acquire("naef"))

    async def test_sources_independent(self) -> None:
        """Test that rate limits for different sources are independent."""
        limiter = RateLimiter({"naef": 10, "burger": 5})
        for _ in range(10):
            await limiter.acquire("naef")
        self.assertFalse(limiter.can_acquire("naef"))
        self.assertTrue(limiter.can_acquire("burger"))

    async def test_zero_rate_raises(self) -> None:
        """Test that initializing a rate limiter with a zero rate raises a ValueError."""
        with self.assertRaises(ValueError):
            RateLimiter({"naef": 0})

    async def test_unconfigured_slug_raises(self) -> None:
        """Test that accessing an unconfigured slug raises a KeyError."""
        limiter = RateLimiter({"naef": 10})
        with self.assertRaises(KeyError):
            await limiter.acquire("burger")
        with self.assertRaises(KeyError):
            limiter.can_acquire("burger")
