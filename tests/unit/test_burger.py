"""Unit tests for the Burger Immobilier scraper (sitemap + fiche pages)."""

import unittest
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from parsel import Selector

from flatpulse.scrapers.sources.burger import BurgerScraper
from tests.contract.test_scraper_contract import ScraperContractMixin
from tests.helpers import response_from_fixture

FICHE = "https://www.burger-sa.ch/fr/louer/"


def fake_get(url: str) -> MagicMock:
    """httpx GET served from fixtures: the sitemap, or the fiche named by its slug."""
    if url == BurgerScraper.sitemap_url:
        return response_from_fixture("burger_sitemap.xml")
    return response_from_fixture(f"burger_fiche_{url.removeprefix(FICHE)}.html")


class TestBurgerScraper(ScraperContractMixin, unittest.IsolatedAsyncioTestCase):
    """Contract and unit tests for BurgerScraper against frozen Burger fixtures."""

    scraper_class = BurgerScraper
    fixture_name = "burger_sitemap.xml"

    async def fetch_from_fixture(self) -> list[dict[str, Any]]:
        """Serve the sitemap and every fiche it lists from their fixtures."""
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = fake_get
            return await self.scraper_class().fetch_listings()

    async def test_parses_every_fiche_of_the_sitemap(self) -> None:
        """Each /fr/louer/ fiche of the sitemap gives one listing, read from its page."""
        listings = {
            x["external_url"].removeprefix(FICHE): x
            for x in await self.fetch_from_fixture()
        }

        self.assertEqual(
            {
                slug: (
                    x["price_chf"],
                    x["nb_rooms"],
                    x["surface_m2"],
                    x["address"],
                    x["city"],
                )
                for slug, x in listings.items()
            },
            {
                "geneve-studio-meuble": (
                    215000,
                    1.0,
                    36.0,
                    "Rue du Mont-Blanc 17",
                    "Genève",
                ),
                # The fiche shows "0.0 pièces": unknown, so None.
                "geneve-appartement-de-charme-et-de-prestige": (
                    700000,
                    None,
                    180.0,
                    "Place du Bourg-de-Four 9",
                    "Genève",
                ),
                # "Dès CHF 2'320.- + charges", no street nor NPA on the fiche.
                "3-pieces-a-louer": (232000, 3.0, 60.0, "Quartier de Champel", None),
                "le-lignon-parking-interne-au-1er-sous-sol": (
                    11900,
                    None,
                    None,
                    "Route du Bois-des-Frères 2 - 2 C",
                    "Le Lignon",
                ),
            },
        )
        studio = listings["geneve-studio-meuble"]
        self.assertEqual(studio["external_id"], studio["external_url"])
        self.assertEqual(studio["title"], "Studio meublé")
        self.assertTrue(studio["description"].startswith("A louer, très beau studio"))
        self.assertEqual(len(studio["images"]), 5)
        for image in studio["images"]:
            self.assertTrue(image.startswith("https://www.burger-sa.ch/corumfiles/"))

    async def test_a_sitemap_without_fiches_is_an_error(self) -> None:
        """A sitemap format change must not pass for "Burger has nothing to rent"."""
        client = AsyncMock()
        client.get.return_value = MagicMock(
            text="<urlset><url><loc>https://www.burger-sa.ch/fr</loc></url></urlset>"
        )

        with self.assertRaises(ValueError):
            await BurgerScraper().listing_pages(client)

    def test_an_unreadable_fiche_is_logged_and_skipped(self) -> None:
        """A fiche without its details block (markup change) is logged, not parsed."""
        page = Selector(
            text=f'<link href="{FICHE}x" rel="canonical"><h1>Studio meublé</h1>'
        )

        with self.assertLogs("flatpulse.scrapers.sources.burger", "WARNING") as logs:
            self.assertEqual(BurgerScraper().listing_nodes(page), [])
        self.assertIn(FICHE + "x", logs.output[0])
