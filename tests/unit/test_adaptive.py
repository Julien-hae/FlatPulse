"""Unit tests for AdaptivePoller.compute_interval (#47)."""

import unittest
from datetime import datetime

from flatpulse.common.models import ScrapingStats, SourceConfig
from flatpulse.scrapers.adaptive_poller import ZURICH, AdaptivePoller

TUESDAY_10AM = datetime(2026, 11, 10, 10, 0, tzinfo=ZURICH)
TUESDAY_11PM = datetime(2026, 11, 10, 23, 0, tzinfo=ZURICH)
SATURDAY_10AM = datetime(2026, 11, 14, 10, 0, tzinfo=ZURICH)

# Some activity in the last six hours, below the "active" threshold: no rule applies.
STEADY = 2


def config(poll_interval_s: int = 120) -> SourceConfig:
    return SourceConfig(
        slug="naef",
        name="Naef Immobilier",
        base_url="https://www.naef.ch",
        scraper_class="NaefScraper",
        poll_interval_s=poll_interval_s,
    )


def poller(now: datetime = TUESDAY_10AM) -> AdaptivePoller:
    return AdaptivePoller(clock=lambda: now)


class TestAdaptivePoller(unittest.TestCase):
    def test_active_source_faster(self) -> None:
        """An agency publishing a lot is polled twice as often."""
        stats = ScrapingStats(new_listings_last_hour=8)

        self.assertEqual(poller().compute_interval(config(120), stats), 60)

    def test_inactive_source_slower(self) -> None:
        """Nothing new in six hours: half as many requests."""
        stats = ScrapingStats(new_listings_last_6h=0)

        self.assertEqual(poller().compute_interval(config(120), stats), 240)

    def test_errors_backoff(self) -> None:
        """A site down is not hammered: 120 x 2³, capped at 600."""
        stats = ScrapingStats(new_listings_last_6h=STEADY, consecutive_errors=3)

        self.assertEqual(poller().compute_interval(config(120), stats), 600)

    def test_errors_backoff_below_the_cap(self) -> None:
        """One error doubles the interval."""
        stats = ScrapingStats(new_listings_last_6h=STEADY, consecutive_errors=1)

        self.assertEqual(poller().compute_interval(config(120), stats), 240)

    def test_bounds_respected(self) -> None:
        """Never more than one poll per 30 s, never less than one per 600 s."""
        cases = {
            "very active": (config(30), ScrapingStats(new_listings_last_hour=8)),
            "many errors": (
                config(120),
                ScrapingStats(new_listings_last_6h=STEADY, consecutive_errors=10),
            ),
            "down for days": (
                config(120),
                ScrapingStats(new_listings_last_6h=STEADY, consecutive_errors=5000),
            ),
        }
        for name, (source, stats) in cases.items():
            with self.subTest(name):
                interval = poller().compute_interval(source, stats)
                self.assertGreaterEqual(interval, 30)
                self.assertLessEqual(interval, 600)
        self.assertEqual(poller().compute_interval(*cases["very active"]), 30)
        self.assertEqual(poller().compute_interval(*cases["many errors"]), 600)

    def test_night_and_weekend_slower(self) -> None:
        """Agencies publish during office hours: three times slower outside them."""
        stats = ScrapingStats(new_listings_last_6h=STEADY)

        self.assertEqual(poller().compute_interval(config(120), stats), 120)
        for name, now in {"night": TUESDAY_11PM, "weekend": SATURDAY_10AM}.items():
            with self.subTest(name):
                self.assertEqual(poller(now).compute_interval(config(120), stats), 360)
