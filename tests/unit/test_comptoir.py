"""Unit tests for the Comptoir Immobilier scraper."""

import unittest
from typing import Any
from unittest.mock import AsyncMock, patch

from flatpulse.scrapers.base import REQUIRED_FIELDS
from flatpulse.scrapers.sources.comptoir import ComptoirScraper
from tests.contract.test_scraper_contract import ScraperContractMixin
from tests.helpers import response_from_fixture


class TestComptoirScraper(ScraperContractMixin, unittest.IsolatedAsyncioTestCase):
    """Contract and unit tests for ComptoirScraper.

    The fixture holds the whole catalogue (pages 1 to 16 of 30.10.2026) without its
    pagination, so a single mocked GET returns every card.
    """

    scraper_class = ComptoirScraper
    fixture_name = "comptoir_listing.html"

    async def listing(self, external_id: str) -> dict[str, Any]:
        """Return the fixture listing whose external_id matches."""
        listings = await self.fetch_from_fixture()
        return next(item for item in listings if item["external_id"] == external_id)

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    async def test_parse_comptoir_fixture(self, mock_get: AsyncMock) -> None:
        """fetch_listings turns every card of the fixture into a listing."""
        mock_get.return_value = response_from_fixture(self.fixture_name)

        result = await ComptoirScraper().fetch_listings()

        self.assertEqual(len(result), 374)
        for item in result:
            self.assertIsInstance(item, dict)
            for field in REQUIRED_FIELDS:
                self.assertIn(field, item, item)
                self.assertTrue(item[field], f"{field}: {item}")
            self.assertIsInstance(item["price_chf"], (int, type(None)))
            self.assertIsInstance(item["nb_rooms"], (float, type(None)))
            self.assertIsInstance(item["surface_m2"], (float, type(None)))
