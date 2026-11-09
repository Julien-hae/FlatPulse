"""Opt-in live integration tests for scraper catalogues."""

import asyncio
import logging
import os
import unittest

from flatpulse.common.models import Listing, PropertyType
from flatpulse.common.postal_codes import (
    CantonLookup,
    download_swisstopo,
    fill_missing_canton,
)
from flatpulse.scrapers.base import HttpScraper
from flatpulse.scrapers.rate_limiter import RateLimiter
from flatpulse.scrapers.sources.burger import BurgerScraper
from flatpulse.scrapers.sources.comptoir import ComptoirScraper
from flatpulse.scrapers.sources.naef import NaefScraper
from tests.live_report import (
    Thresholds,
    fetch_catalogues,
    fill_rate_shortfalls,
    format_fill_rate_report,
    format_supply_distribution,
    skipped_listings,
)

logger = logging.getLogger(__name__)

SCRAPER_CLASSES: tuple[type[HttpScraper], ...] = (
    NaefScraper,
    BurgerScraper,
    ComptoirScraper,
)
# Requests per minute measured for each agency, see docs/spike-agencies.md
# (Comptoir: Crawl-delay of 10 s).
RATE_LIMITS_RPM = {"naef": 10, "burger": 4, "comptoir": 6}

# Fill rates of the run of 08.11.2026, 12:12 UTC (docs/live-audit.md), less 10 points,
# rounded down to 5 %. Only types with at least 20 listings that day, and only rates
# above 0 %: below that, one listing more or less moves the rate past any margin.
# Fields without a threshold (Comptoir postal_code, not published; surface and rooms
# of parkings) are still in the report. A threshold lowered to pass must say why here.
MIN_FILL_RATE: Thresholds = {
    "naef": {
        PropertyType.APARTMENT: {
            "price_chf": 0.85,
            "surface_m2": 0.65,
            "nb_rooms": 0.85,
            "postal_code": 0.9,
            "canton": 0.9,
            "images": 0.9,
        },
        PropertyType.COMMERCIAL: {
            "price_chf": 0.75,
            "surface_m2": 0.75,
            "postal_code": 0.9,
            "canton": 0.9,
            "images": 0.9,
        },
        PropertyType.HOUSE: {
            "price_chf": 0.55,
            "surface_m2": 0.85,
            "nb_rooms": 0.6,
            "postal_code": 0.9,
            "canton": 0.9,
            "images": 0.9,
        },
        PropertyType.PARKING: {
            "price_chf": 0.85,
            "postal_code": 0.9,
            "canton": 0.9,
            "images": 0.9,
        },
    },
    "burger": {
        PropertyType.APARTMENT: {
            "price_chf": 0.9,
            "surface_m2": 0.8,
            "nb_rooms": 0.85,
            "postal_code": 0.9,
            "canton": 0.9,
            "images": 0.75,
        },
    },
    "comptoir": {
        PropertyType.APARTMENT: {
            "price_chf": 0.9,
            "surface_m2": 0.5,
            "nb_rooms": 0.9,
            "canton": 0.9,
            "images": 0.85,
        },
        PropertyType.COMMERCIAL: {
            "price_chf": 0.85,
            "surface_m2": 0.85,
            "canton": 0.9,
            "images": 0.85,
        },
        PropertyType.PARKING: {
            "price_chf": 0.85,
            "canton": 0.9,
            "images": 0.35,
        },
        PropertyType.STORAGE: {
            "price_chf": 0.7,
            "surface_m2": 0.7,
            "canton": 0.9,
            "images": 0.65,
        },
    },
}


@unittest.skipUnless(
    os.environ.get("FLATPULSE_LIVE") == "1",
    "Set FLATPULSE_LIVE=1 to run live source audits.",
)
class LiveSourcesTest(unittest.TestCase):
    """Check live catalogues and field coverage without running in default suites."""

    catalogues: dict[str, list[Listing]]
    fetch_errors: dict[str, str]
    invalid_listing_messages: list[str]

    @classmethod
    def setUpClass(cls) -> None:
        """Fetch each catalogue once per run: this is real traffic at the agency."""
        super().setUpClass()
        rate_limiter = RateLimiter(RATE_LIMITS_RPM)
        scrapers = [
            scraper_class(rate_limiter=rate_limiter)
            for scraper_class in SCRAPER_CLASSES
        ]
        with skipped_listings() as skipped:
            cls.catalogues, cls.fetch_errors = asyncio.run(fetch_catalogues(scrapers))
        cls.invalid_listing_messages = skipped
        # The audit measures what the pipeline carries: the canton a source leaves
        # out is completed from the postal code (#133), from swisstopo's directory
        # rather than the database, which this audit does not need.
        lookup = CantonLookup(download_swisstopo())
        cls.catalogues = {
            source: [fill_missing_canton(listing, lookup) for listing in listings]
            for source, listings in cls.catalogues.items()
        }
        logger.info(
            "Live supply distribution:\n%s\n\nLive fill-rate report:\n%s",
            format_supply_distribution(cls.catalogues),
            format_fill_rate_report(cls.catalogues),
        )

    def test_live_catalogue_is_not_empty(self) -> None:
        """Every source answers with listings, none of them skipped as invalid."""
        for scraper_class in SCRAPER_CLASSES:
            source = scraper_class.slug
            with self.subTest(source=source):
                self.assertNotIn(
                    source,
                    self.fetch_errors,
                    f"{source} fetch failed: {self.fetch_errors.get(source)}",
                )
                self.assertTrue(
                    self.catalogues[source], f"{source} returned an empty catalogue"
                )
        self.assertFalse(
            self.invalid_listing_messages,
            "Listings were skipped as invalid:\n"
            + "\n".join(self.invalid_listing_messages),
        )

    def test_live_fill_rates(self) -> None:
        """Every field is at or above its MIN_FILL_RATE; a failure shows the full table."""
        shortfalls = fill_rate_shortfalls(self.catalogues, MIN_FILL_RATE)

        self.assertFalse(
            shortfalls,
            "Fill rates under their threshold:\n"
            + "\n".join(shortfalls)
            + "\n\n"
            + format_fill_rate_report(self.catalogues),
        )
