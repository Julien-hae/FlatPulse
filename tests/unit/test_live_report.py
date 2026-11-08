"""Tests for the live scraper audit report."""

import asyncio
import logging
import unittest
from unittest import mock

import httpx

from flatpulse.common.models import Listing, PropertyType
from flatpulse.scrapers.base import HttpScraper
from tests.live_report import (
    FillCount,
    Thresholds,
    calculate_fill_rates,
    fetch_catalogues,
    fill_rate_shortfalls,
    format_fill_rate_report,
    skipped_listings,
)


def _scraper(slug: str, outcome: list[Listing] | Exception) -> mock.Mock:
    """Return a scraper whose `fetch_listings` yields `outcome` or raises it."""
    scraper: mock.Mock = mock.create_autospec(HttpScraper, instance=True)
    scraper.slug = slug
    if isinstance(outcome, Exception):
        scraper.fetch_listings.side_effect = outcome
    else:
        scraper.fetch_listings.return_value = outcome
    return scraper


def _apartments(*surfaces: float | None) -> list[Listing]:
    """Geneva apartments, one per surface, the other fields left empty."""
    return [
        Listing(
            external_id=str(index),
            external_url=f"https://example.test/{index}",
            title="Appartement à Genève",
            property_type=PropertyType.APARTMENT,
            surface_m2=surface,
        )
        for index, surface in enumerate(surfaces, start=1)
    ]


class LiveReportTest(unittest.TestCase):
    """Tests for live audit reporting and incremental persistence."""

    def test_surface_fill_rate_is_two_thirds(self) -> None:
        report = calculate_fill_rates(_apartments(50, None, 70), ("surface_m2",))

        self.assertEqual(report[PropertyType.APARTMENT]["surface_m2"], FillCount(2, 3))
        self.assertEqual(report[PropertyType.APARTMENT]["surface_m2"].rate, 2 / 3)

    def test_fill_rates_cover_city_and_canton(self) -> None:
        """canton and city are audited: #131 was a canton unknown on 283 listings."""
        report = calculate_fill_rates(_apartments(50))

        self.assertIn("canton", report[PropertyType.APARTMENT])
        self.assertIn("city", report[PropertyType.APARTMENT])

    def test_fill_rate_report_lists_all_sources_and_fields(self) -> None:
        [listing] = _apartments(50)

        report = format_fill_rate_report({"naef": [listing], "burger": [listing]})

        self.assertIn("naef | apartment | surface_m2 | 1/1 | 100.0%", report)
        self.assertIn("burger | apartment | price_chf | 0/1 | 0.0%", report)
        self.assertIn("burger | apartment | canton | 0/1 | 0.0%", report)

    def test_fill_rate_shortfalls_name_each_field_under_its_threshold(self) -> None:
        """A rate under its threshold is reported; a rate at or above it is not."""
        catalogues = {"naef": _apartments(50, None, 70)}
        thresholds: Thresholds = {
            "naef": {PropertyType.APARTMENT: {"surface_m2": 0.9, "nb_rooms": 0.0}}
        }

        shortfalls = fill_rate_shortfalls(catalogues, thresholds)

        self.assertEqual(shortfalls, ["naef | apartment | surface_m2 : 66.7% < 90%"])

    def test_fill_rate_shortfalls_flag_a_type_gone_missing(self) -> None:
        """A type with thresholds and no listing left means the scraper lost it."""
        catalogues = {"naef": _apartments(50)}
        thresholds: Thresholds = {"naef": {PropertyType.PARKING: {"price_chf": 0.85}}}

        shortfalls = fill_rate_shortfalls(catalogues, thresholds)

        self.assertEqual(shortfalls, ["naef | parking : aucune annonce"])

    def test_fill_rate_shortfalls_skip_a_source_not_fetched(self) -> None:
        """A source down is test_live_catalogue_is_not_empty's failure, not this one."""
        thresholds: Thresholds = {"naef": {PropertyType.APARTMENT: {"surface_m2": 0.9}}}

        self.assertEqual(fill_rate_shortfalls({}, thresholds), [])

    def test_skipped_listings_collects_invalid_listings_only(self) -> None:
        """The listings HttpScraper skips as invalid are collected, nothing else."""

        def invalid() -> Listing:
            raise ValueError("title cannot be empty")

        base_logger = logging.getLogger("flatpulse.scrapers.base")
        with self.assertLogs(base_logger), skipped_listings() as skipped:
            HttpScraper._parse_or_skip(invalid)
            base_logger.warning("Fiche %s : connexion coupée", "https://example.test")

        self.assertEqual(skipped, ["Skipped invalid listing: title cannot be empty"])

    def test_fetch_catalogues_goes_on_when_a_source_is_down(self) -> None:
        listing = Listing(
            external_id="1",
            external_url="https://example.test/1",
            title="Appartement à Carouge",
        )
        scrapers = [
            _scraper("naef", [listing]),
            _scraper("burger", httpx.ConnectError("Network is unreachable")),
            _scraper("comptoir", [listing]),
        ]

        catalogues, errors = asyncio.run(fetch_catalogues(scrapers))

        self.assertEqual(catalogues, {"naef": [listing], "comptoir": [listing]})
        self.assertEqual(errors, {"burger": "ConnectError: Network is unreachable"})

    def test_fetch_catalogues_logs_each_source_before_the_next_one(self) -> None:
        listing = Listing(
            external_id="1",
            external_url="https://example.test/1",
            title="Appartement à Lancy",
            property_type=PropertyType.APARTMENT,
            canton="GE",
        )
        scrapers = [
            _scraper("naef", [listing]),
            _scraper("burger", httpx.ConnectError("Network is unreachable")),
        ]

        with self.assertLogs("tests.live_report") as logs:
            asyncio.run(fetch_catalogues(scrapers))

        output = "\n".join(logs.output)
        self.assertIn("naef | apartment | GE | 1", output)
        self.assertIn("naef | apartment | surface_m2 | 0/1 | 0.0%", output)
        self.assertIn("ERROR:tests.live_report:burger", output)
