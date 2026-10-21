"""Unit tests for the Burger Immobilier scraper."""

import unittest
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from parsel import Selector

from flatpulse.scrapers.sources.burger import BurgerScraper
from tests.contract.test_scraper_contract import ScraperContractMixin
from tests.helpers import response_from_fixture

URL = "https://www.burger-sa.ch/fr/louer/geneve-appartement-de-charme-et-de-prestige"
SITEMAP = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://www.burger-sa.ch/fr/acheter/duplex-a-bernex</loc></url>
<url><loc>{URL}</loc></url>
</urlset>"""


def fake_get(url: str) -> MagicMock:
    """Serve the sitemap above, and the frozen fiche for its rental entry."""
    if url == BurgerScraper.base_url:
        return MagicMock(text=SITEMAP)
    return response_from_fixture("burger_fiche.html")


class TestBurgerScraper(ScraperContractMixin, unittest.IsolatedAsyncioTestCase):
    """Contract and unit tests for BurgerScraper."""

    scraper_class = BurgerScraper
    fixture_name = "burger_fiche.html"

    async def fetch_from_fixture(self) -> list[dict[str, Any]]:
        """Serve the sitemap, then its rental fiche."""
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = fake_get
            return await self.scraper_class().fetch_listings()

    async def test_parses_each_rental_fiche_of_the_sitemap(self) -> None:
        """Only /fr/louer/ fiches are parsed; "0.0 pièces" means an unknown count."""
        [listing] = await self.fetch_from_fixture()

        self.assertEqual(listing["external_id"], URL)
        self.assertEqual(listing["title"], "Appartement de charme et de prestige")
        self.assertEqual(listing["price_chf"], 700000)
        self.assertIsNone(listing["nb_rooms"])
        self.assertEqual(listing["surface_m2"], 180.0)
        self.assertEqual(listing["address"], "Place du Bourg-de-Four 9")
        self.assertEqual(listing["city"], "Genève")
        self.assertTrue(
            listing["description"].startswith("Au coeur de la Vieille-Ville")
        )
        self.assertEqual(len(listing["images"]), 3)
        for image in listing["images"]:
            self.assertTrue(image.startswith("https://www.burger-sa.ch/corumfiles/"))

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    async def test_a_failing_fiche_is_skipped(self, mock_get: AsyncMock) -> None:
        """A fiche that cannot be downloaded is logged and does not fail the poll."""

        def get(url: str) -> MagicMock:
            if url == URL:
                raise httpx.ConnectError("Server disconnected")
            return fake_get(url)

        mock_get.side_effect = get
        with self.assertLogs("flatpulse.scrapers.sources.burger", "WARNING"):
            self.assertEqual(await BurgerScraper().fetch_listings(), [])

    def test_parse_listing_falls_back_to_the_canonical_url(self) -> None:
        """Called through the base contract, without `url`, the fiche names itself."""
        page = Selector(text=response_from_fixture("burger_fiche.html").text)

        self.assertEqual(BurgerScraper().parse_listing(page)["external_url"], URL)

    def test_an_empty_description_is_none(self) -> None:
        """An empty description block is an absent field, not an empty string."""
        page = Selector(text='<div class="prose">  </div>')

        self.assertIsNone(BurgerScraper().parse_listing(page, URL)["description"])

    def test_city_needs_a_npa_line(self) -> None:
        """The city comes from the "NPA town" line only; anything else is None."""
        self.assertEqual(BurgerScraper.city(["Rue X 1", "1204 Genève"]), "Genève")
        self.assertIsNone(BurgerScraper.city(["Quartier de Champel"]))
        self.assertIsNone(BurgerScraper.city(["Rue X 1", "Genève"]))
