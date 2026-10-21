"""Unit tests for the Burger Immobilier scraper."""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

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

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    async def test_stops_when_a_page_brings_nothing_new(
        self, mock_get: AsyncMock
    ) -> None:
        """Infinite scroll gives no page count: walk pages until one repeats or is empty."""
        mock_get.return_value = response_from_fixture(self.fixture_name)

        await self.scraper_class().fetch_listings()

        self.assertEqual(
            [call.args[0] for call in mock_get.call_args_list][:2],
            [
                "https://www.burger-sa.ch/fr/louer?page=1",
                "https://www.burger-sa.ch/fr/louer?page=2",
            ],
        )

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    async def test_warns_about_sitemap_listings_missing_from_pages(
        self, mock_get: AsyncMock
    ) -> None:
        """Every /fr/louer/ fiche of the sitemap not reached by scrolling is logged."""
        mock_get.side_effect = lambda url: response_from_fixture(
            "burger_sitemap.txt" if "sitemap" in url else self.fixture_name
        )

        with self.assertLogs("flatpulse.scrapers.sources.burger", "WARNING") as logs:
            await self.scraper_class().fetch_listings()

        warning = logs.output[0]
        self.assertIn("23", warning)  # 27 fiches in the sitemap, 4 on the pages
        self.assertIn("/fr/louer/geneve-studio-meuble", warning)
        self.assertNotIn("/fr/louer/3-pieces-a-louer", warning)

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    async def test_keeps_dwellings_by_type_and_never_zero_rooms(
        self, mock_get: AsyncMock
    ) -> None:
        """Dwellings are told apart by their type label; a site-side 0.0 rooms is unknown."""
        card = (
            '<div class="bien-item"><a href="/fr/louer/{slug}"></a>'
            '<div class="font-bold">CHF 1\'000.-</div><h2>Genève</h2>'
            '<div class="text-primary">{kind}</div></div>'
        )
        html = "".join(
            card.format(slug=slug, kind=kind)
            for slug, kind in [
                ("charme", "Appartement  0.0 pièces"),
                ("villa", "Maison  5.0 pièces"),
                ("depot", "Dépôt"),
                ("parking", "Place ouverte"),
            ]
        )
        mock_get.side_effect = lambda url: MagicMock(
            text=html if url.endswith("page=1") else ""
        )

        listings = await self.scraper_class().fetch_listings()

        self.assertEqual(
            [(x["external_url"].rsplit("/", 1)[-1], x["nb_rooms"]) for x in listings],
            [("charme", None), ("villa", 5.0)],
        )
