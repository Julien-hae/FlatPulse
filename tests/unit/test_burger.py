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

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    async def test_parse_burger_fixture(self, mock_get: AsyncMock) -> None:
        """price_chf, nb_rooms and surface_m2 are each read from their own card text."""
        mock_get.return_value = response_from_fixture(self.fixture_name)
        html = mock_get.return_value.text
        page = Selector(text=html)
        listings = [
            self.scraper_class().parse_listing(node)
            for node in self.scraper_class().listing_nodes(page)
        ]
        self.assertGreaterEqual(len(listings), 2)
        self.assertEqual(
            [listing["price_chf"] for listing in listings],
            [232000, 315000, 40000, 350000],
        )
        self.assertEqual(
            [listing["nb_rooms"] for listing in listings],
            [3.0, 4.0, None, 5.0],
        )
        self.assertEqual(
            [listing["surface_m2"] for listing in listings],
            [60.0, 85.0, None, 121.0],
        )

    async def test_external_id_is_full_url(self) -> None:
        """external_id is the full listing URL, not a truncated slug that can collide."""
        page = Selector(text=response_from_fixture(self.fixture_name).text)
        listings = [
            self.scraper_class().parse_listing(node)
            for node in self.scraper_class().listing_nodes(page)
        ]
        for listing in listings:
            self.assertEqual(listing["external_id"], listing["external_url"])

    async def test_images_are_absolute_urls(self) -> None:
        """Image URLs are resolved against base_url, never left relative."""
        page = Selector(text=response_from_fixture(self.fixture_name).text)
        listings = [
            self.scraper_class().parse_listing(node)
            for node in self.scraper_class().listing_nodes(page)
        ]
        for listing in listings:
            for image in listing["images"]:
                self.assertTrue(image.startswith("http"), image)

    @patch("asyncio.sleep", new_callable=AsyncMock)
    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    async def test_filters_non_apartment_listings(
        self, mock_get: AsyncMock, mock_sleep: AsyncMock
    ) -> None:
        """Parking/commercial cards (no room count on the card) are dropped."""
        mock_get.return_value = response_from_fixture(self.fixture_name)
        listings = await self.scraper_class().fetch_listings()
        self.assertTrue(
            all(
                "places-de-parking" not in listing["external_url"]
                for listing in listings
            )
        )

    @patch("asyncio.sleep", new_callable=AsyncMock)
    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    async def test_paginates_across_all_pages(
        self, mock_get: AsyncMock, mock_sleep: AsyncMock
    ) -> None:
        """fetch_listings requests all 6 pages documented in docs/spike-agencies.md."""
        mock_get.return_value = response_from_fixture(self.fixture_name)
        await self.scraper_class().fetch_listings()
        requested_urls = [call.args[0] for call in mock_get.call_args_list]
        self.assertEqual(len(requested_urls), 6)
        for page_number, url in enumerate(requested_urls, start=1):
            self.assertIn(f"page={page_number}", url)
        # Pace the 6 requests instead of firing them back-to-back.
        self.assertEqual(mock_sleep.await_count, 5)
