"""Tests for the live scraper audit report."""

import unittest

from flatpulse.common.models import Listing, PropertyType
from tests.integration.live_report import (
    calculate_fill_rates,
    format_fill_rate_report,
)


class LiveReportTest(unittest.TestCase):
    """Tests for live audit reporting and incremental persistence."""

    def test_surface_fill_rate_is_two_thirds(self) -> None:
        listings = [
            Listing(
                external_id=str(index),
                external_url=f"https://example.test/{index}",
                title="Appartement à Genève",
                property_type=PropertyType.APARTMENT,
                surface_m2=surface,
            )
            for index, surface in enumerate((50, None, 70), start=1)
        ]

        report = calculate_fill_rates(listings, ("surface_m2",))

        self.assertEqual(
            report[PropertyType.APARTMENT]["surface_m2"],
            2 / 3,
        )

    def test_fill_rate_report_lists_all_sources_and_fields(self) -> None:
        listing = Listing(
            external_id="1",
            external_url="https://example.test/1",
            title="Appartement à Genève",
            property_type=PropertyType.APARTMENT,
            surface_m2=50,
        )

        report = format_fill_rate_report({"naef": [listing], "burger": [listing]})

        self.assertIn("naef | apartment | surface_m2 | 1/1 | 100.0%", report)
        self.assertIn("burger | apartment | price_chf | 0/1 | 0.0%", report)
