"""Unit tests for the Burger Immobilier scraper."""

import unittest
from unittest.mock import AsyncMock, patch

from parsel import Selector

from flatpulse.scrapers.sources.burger import BurgerScraper
from tests.contract.test_scraper_contract import ScraperContractMixin
from tests.helpers import response_from_fixture


class TestBurgerScraper(ScraperContractMixin, unittest.IsolatedAsyncioTestCase):
    """Contract and unit tests for BurgerScraper against the frozen Burger JSON fixture."""

    scraper_class = BurgerScraper
    fixture_name = "burger_listing.html"

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    async def test_parse_burger_fixture(self, mock_get: AsyncMock) -> None:
        """Test parsing the Burger Immobilier HTML fixture."""
        mock_get.return_value = response_from_fixture(self.fixture_name)
        html = mock_get.return_value.text
        page = Selector(text=html)
        listings = [
            self.scraper_class().parse_listing(node)
            for node in self.scraper_class().listing_nodes(page)
        ]
        self.assertGreaterEqual(len(listings), 2)
