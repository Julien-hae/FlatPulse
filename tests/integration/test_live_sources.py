"""Opt-in live integration tests for scraper catalogues."""

import asyncio
import logging
import os
import unittest
from collections import Counter
from collections.abc import Mapping, Sequence

from flatpulse.common.models import Listing
from flatpulse.scrapers.base import HttpScraper
from flatpulse.scrapers.rate_limiter import RateLimiter
from flatpulse.scrapers.sources.burger import BurgerScraper
from flatpulse.scrapers.sources.comptoir import ComptoirScraper
from flatpulse.scrapers.sources.naef import NaefScraper
from tests.integration.live_report import format_fill_rate_report

logger = logging.getLogger(__name__)
_BASE_SCRAPER_LOGGER = logging.getLogger("flatpulse.scrapers.base")

SCRAPER_CLASSES: tuple[type[HttpScraper], ...] = (
    NaefScraper,
    BurgerScraper,
    ComptoirScraper,
)
RATE_LIMITS_RPM = {"naef": 10, "burger": 4, "comptoir": 6}


class _SkippedInvalidListingHandler(logging.Handler):
    """Collect Listing validation warnings produced during the live fetch."""

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        message = record.getMessage()
        if message.startswith("Skipped invalid listing:"):
            self.messages.append(message)


@unittest.skipUnless(
    os.environ.get("FLATPULSE_LIVE") == "1",
    "Set FLATPULSE_LIVE=1 to run live source audits.",
)
class LiveSourcesTest(unittest.IsolatedAsyncioTestCase):
    """Check live catalogues and field coverage without running in default suites."""

    catalogues: dict[str, list[Listing]]
    invalid_listing_messages: list[str]

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        handler = _SkippedInvalidListingHandler()
        _BASE_SCRAPER_LOGGER.addHandler(handler)
        try:
            cls.catalogues = asyncio.run(cls._fetch_catalogues())
        finally:
            _BASE_SCRAPER_LOGGER.removeHandler(handler)
        cls.invalid_listing_messages = handler.messages
        _log_supply_distribution(cls.catalogues)

    @classmethod
    async def _fetch_catalogues(cls) -> dict[str, list[Listing]]:
        rate_limiter = RateLimiter(RATE_LIMITS_RPM)
        catalogues: dict[str, list[Listing]] = {}
        for scraper_class in SCRAPER_CLASSES:
            scraper = scraper_class(rate_limiter=rate_limiter)
            catalogues[scraper.slug] = await scraper.fetch_listings()
        return catalogues

    async def test_live_catalogue_is_not_empty(self) -> None:
        for source, listings in self.catalogues.items():
            with self.subTest(source=source):
                self.assertTrue(listings, f"{source} returned an empty catalogue")
        self.assertFalse(
            self.invalid_listing_messages,
            "Listings were skipped as invalid:\n"
            + "\n".join(self.invalid_listing_messages),
        )

    async def test_live_fill_rates(self) -> None:
        report = format_fill_rate_report(self.catalogues)
        logger.info("Live fill-rate report:\n%s", report)
        self.assertIn("price_chf", report)


def _log_supply_distribution(
    catalogues: Mapping[str, Sequence[Listing]],
) -> None:
    """Log the live listing count by source, property type, and canton."""
    counts = Counter(
        (
            source,
            listing.property_type.value if listing.property_type else "unknown",
            listing.canton or "unknown",
        )
        for source, listings in catalogues.items()
        for listing in listings
    )
    rows = [
        "source | property_type | canton | listings",
        "--- | --- | --- | ---:",
    ]
    rows.extend(
        f"{source} | {property_type} | {canton} | {count}"
        for (source, property_type, canton), count in sorted(counts.items())
    )
    logger.info("Live supply distribution:\n%s", "\n".join(rows))
