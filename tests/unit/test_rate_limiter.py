"""Unit tests for the RateLimiter class."""

import unittest
from unittest.mock import patch

from flatpulse.scrapers.rate_limiter import RateLimiter


class TestRateLimiter(unittest.IsolatedAsyncioTestCase):
    """Unit tests for the RateLimiter class."""

    async def test_acquire_within_limit(self) -> None:
        """Test acquiring tokens within the rate limit."""
        with patch("flatpulse.scrapers.rate_limiter.time.monotonic") as fake_clock:
            fake_clock.return_value = 1000.0
            limiter = RateLimiter({"naef": 10})
            for _ in range(10):
                self.assertTrue(limiter.can_acquire("naef"))
                await limiter.acquire("naef")
                self.assertFalse(limiter.can_acquire("naef"))
                fake_clock.return_value += 6

    async def test_acquire_blocks_over_limit(self) -> None:
        """Test that acquiring tokens blocks when over the rate limit."""

        async def advance_clock(delay: float) -> None:
            fake_clock.return_value += delay

        with patch("flatpulse.scrapers.rate_limiter.time.monotonic") as fake_clock:
            fake_clock.return_value = 1000.0
            limiter = RateLimiter({"naef": 5})
            self.assertTrue(limiter.can_acquire("naef"))
            await limiter.acquire("naef")
            self.assertFalse(limiter.can_acquire("naef"))

            with patch(
                "flatpulse.scrapers.rate_limiter.asyncio.sleep",
                side_effect=advance_clock,
            ) as fake_sleep:
                await limiter.acquire("naef")
            fake_sleep.assert_awaited_once_with(12.0)
            self.assertFalse(limiter.can_acquire("naef"))

    async def test_tokens_refill_over_time(self) -> None:
        """Test that tokens are refilled over time."""
        with patch("flatpulse.scrapers.rate_limiter.time.monotonic") as fake_clock:
            fake_clock.return_value = 1000.0
            limiter = RateLimiter({"naef": 5})
            await limiter.acquire("naef")
            self.assertFalse(limiter.can_acquire("naef"))

            fake_clock.return_value += 11
            self.assertFalse(limiter.can_acquire("naef"))
            fake_clock.return_value += 1
            self.assertTrue(limiter.can_acquire("naef"))
            self.assertTrue(limiter.can_acquire("naef"))

    async def test_sources_independent(self) -> None:
        """Test that rate limits for different sources are independent."""
        with patch("flatpulse.scrapers.rate_limiter.time.monotonic") as fake_clock:
            fake_clock.return_value = 1000.0
            limiter = RateLimiter({"naef": 10, "burger": 5})
            await limiter.acquire("naef")
            self.assertFalse(limiter.can_acquire("naef"))
            self.assertTrue(limiter.can_acquire("burger"))

    async def test_bucket_does_not_burst(self) -> None:
        """A 6 rpm bucket allows one request every 10 seconds, without a burst."""
        with patch("flatpulse.scrapers.rate_limiter.time.monotonic") as fake_clock:
            fake_clock.return_value = 1000.0
            limiter = RateLimiter({"comptoir": 6})

            await limiter.acquire("comptoir")
            self.assertFalse(limiter.can_acquire("comptoir"))

            fake_clock.return_value += 9
            self.assertFalse(limiter.can_acquire("comptoir"))

            fake_clock.return_value += 1
            self.assertTrue(limiter.can_acquire("comptoir"))

    async def test_idle_bucket_does_not_accumulate_tokens(self) -> None:
        """An idle source still allows only one immediate request."""
        with patch("flatpulse.scrapers.rate_limiter.time.monotonic") as fake_clock:
            fake_clock.return_value = 1000.0
            limiter = RateLimiter({"comptoir": 6})
            await limiter.acquire("comptoir")

            fake_clock.return_value += 120
            self.assertTrue(limiter.can_acquire("comptoir"))
            await limiter.acquire("comptoir")
            self.assertFalse(limiter.can_acquire("comptoir"))

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
