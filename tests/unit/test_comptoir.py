"""Unit tests for the Comptoir Immobilier scraper."""

import unittest
from unittest.mock import AsyncMock, patch

from flatpulse.scrapers.base import REQUIRED_FIELDS
from flatpulse.scrapers.sources.comptoir import ComptoirScraper
from tests.contract.test_scraper_contract import ScraperContractMixin
from tests.helpers import response_from_fixture


class TestComptoirScraper(ScraperContractMixin, unittest.IsolatedAsyncioTestCase):
    """Contract and unit tests for ComptoirScraper."""

    scraper_class = ComptoirScraper
    fixture_name = "comptoir_listing.html"

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    async def test_parse_comptoir_fixture(self, mock_get: AsyncMock) -> None:
        """fetch_listings turns the fixture into listings with the required fields."""
        mock_get.return_value = response_from_fixture(self.fixture_name)

        result = await ComptoirScraper().fetch_listings()

        self.assertGreaterEqual(len(result), 2)
        for item in result:
            self.assertIsInstance(item, dict)
            for field in REQUIRED_FIELDS:
                self.assertIn(field, item)
                self.assertTrue(item[field])
            self.assertIsInstance(item["price_chf"], (int, type(None)))
            self.assertIsInstance(item["nb_rooms"], float)
            self.assertIsInstance(item["surface_m2"], (float, type(None)))
