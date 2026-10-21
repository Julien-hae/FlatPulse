"""Unit tests for the Burger Immobilier scraper."""

import unittest
from unittest.mock import AsyncMock, patch

from parsel import Selector

from flatpulse.scrapers.sources.burger import BurgerScraper
from tests.contract.test_scraper_contract import ScraperContractMixin
from tests.helpers import response_from_fixture


class TestBurgerScraper(ScraperContractMixin, unittest.IsolatedAsyncioTestCase):
    """Contract and unit tests for BurgerScraper against the frozen Burger HTML fixture."""

    scraper_class = BurgerScraper
    fixture_name = "burger_listing.html"

    def test_parse_burger_fixture(self) -> None:
        """Each field is read from its own text; URLs and ids are absolute."""
        page = Selector(text=response_from_fixture(self.fixture_name).text)
        scraper = self.scraper_class()
        listings = [scraper.parse_listing(node) for node in scraper.listing_nodes(page)]

        self.assertEqual(
            [listing["price_chf"] for listing in listings],
            [232000, 315000, 40000, 350000],
        )
        self.assertEqual(
            [listing["nb_rooms"] for listing in listings], [3.0, 4.0, None, 5.0]
        )
        self.assertEqual(
            [listing["surface_m2"] for listing in listings], [60.0, 85.0, None, 121.0]
        )
        for listing in listings:
            self.assertEqual(listing["external_id"], listing["external_url"])
            for image in listing["images"]:
                self.assertTrue(image.startswith("https://"), image)

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    async def test_skips_parking_listings(self, mock_get: AsyncMock) -> None:
        """The parking card of the fixture is not returned."""
        mock_get.return_value = response_from_fixture(self.fixture_name)

        listings = await self.scraper_class().fetch_listings()

        self.assertEqual(len(listings), 3)
        self.assertNotIn(
            "parking", " ".join(listing["external_url"] for listing in listings)
        )
