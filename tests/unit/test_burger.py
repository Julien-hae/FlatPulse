"""Unit tests for the Burger Immobilier scraper (sitemap + fiche pages)."""

import unittest
from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from parsel import Selector

from flatpulse.scrapers.sources.burger import BurgerScraper
from tests.contract.test_scraper_contract import ScraperContractMixin
from tests.helpers import response_from_fixture

FICHE = "https://www.burger-sa.ch/fr/louer/"
SITEMAP = response_from_fixture("burger_sitemap.xml").text


def serve(sitemap: str = SITEMAP) -> Callable[[str], MagicMock]:
    """Fake httpx GET: the given sitemap, and each fiche from its frozen fixture."""

    def get(url: str) -> MagicMock:
        if url == BurgerScraper.sitemap_url:
            return MagicMock(text=sitemap)
        return response_from_fixture(f"burger_fiche_{url.removeprefix(FICHE)}.html")

    return get


class TestBurgerScraper(ScraperContractMixin, unittest.IsolatedAsyncioTestCase):
    """Contract and unit tests for BurgerScraper against frozen Burger fixtures."""

    scraper_class = BurgerScraper
    fixture_name = "burger_sitemap.xml"

    async def fetch_from_fixture(self) -> list[dict[str, Any]]:
        """Serve the sitemap and every fiche it lists from their fixtures."""
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = serve()
            return await self.scraper_class().fetch_listings()

    def test_parse_fiche(self) -> None:
        """Every field comes from the fiche itself, not the similar-listing cards."""
        page = Selector(
            text=response_from_fixture("burger_fiche_geneve-studio-meuble.html").text
        )
        scraper = BurgerScraper()
        [node] = scraper.listing_nodes(page)

        listing = scraper.parse_listing(node)

        self.assertEqual(listing["external_url"], FICHE + "geneve-studio-meuble")
        self.assertEqual(listing["external_id"], listing["external_url"])
        self.assertEqual(listing["title"], "Studio meublé")
        self.assertEqual(listing["price_chf"], 215000)
        self.assertEqual(listing["nb_rooms"], 1.0)
        self.assertEqual(listing["surface_m2"], 36.0)
        self.assertEqual(listing["address"], "Rue du Mont-Blanc 17")
        self.assertEqual(listing["city"], "Genève")
        self.assertTrue(listing["description"].startswith("A louer, très beau studio"))
        self.assertEqual(len(listing["images"]), 5)
        for image in listing["images"]:
            self.assertTrue(image.startswith("https://www.burger-sa.ch/corumfiles/"))

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    async def test_parses_every_fiche_of_the_sitemap(self, mock_get: AsyncMock) -> None:
        """Each rental fiche of the sitemap is fetched; non-rental URLs are not."""
        mock_get.side_effect = serve()

        await BurgerScraper().fetch_listings()

        self.assertEqual(
            sorted(call.args[0] for call in mock_get.call_args_list),
            sorted(
                [
                    BurgerScraper.sitemap_url,
                    FICHE + "3-pieces-a-louer",
                    FICHE + "geneve-appartement-de-charme-et-de-prestige",
                    FICHE + "geneve-studio-meuble",
                    FICHE + "le-lignon-parking-interne-au-1er-sous-sol",
                ]
            ),
        )

    async def test_returns_every_fiche(self) -> None:
        """Every fiche becomes a listing; a "0.0 pièces" or a parking has no room count."""
        listings = await self.fetch_from_fixture()

        by_slug = {x["external_url"].removeprefix(FICHE): x for x in listings}
        self.assertEqual(
            sorted(by_slug),
            [
                "3-pieces-a-louer",
                "geneve-appartement-de-charme-et-de-prestige",
                "geneve-studio-meuble",
                "le-lignon-parking-interne-au-1er-sous-sol",
            ],
        )
        self.assertIsNone(
            by_slug["geneve-appartement-de-charme-et-de-prestige"]["nb_rooms"]
        )
        self.assertIsNone(
            by_slug["le-lignon-parking-interne-au-1er-sous-sol"]["nb_rooms"]
        )
        self.assertEqual(by_slug["3-pieces-a-louer"]["price_chf"], 232000)

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    async def test_a_sitemap_without_fiches_is_an_error(
        self, mock_get: AsyncMock
    ) -> None:
        """A sitemap format change must not pass for "Burger has nothing to rent"."""
        mock_get.side_effect = serve(SITEMAP.replace("/fr/louer/", "/fr/rent/"))

        with self.assertRaises(ValueError):
            await BurgerScraper().fetch_listings()

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    async def test_an_unreadable_fiche_is_logged(self, mock_get: AsyncMock) -> None:
        """A fiche without its rent block (markup change) is logged and skipped."""
        fiches = serve()

        def get(url: str) -> MagicMock:
            if url == FICHE + "geneve-studio-meuble":
                return MagicMock(
                    text="<html><body><h1>Studio meublé</h1></body></html>"
                )
            return fiches(url)

        mock_get.side_effect = get
        with self.assertLogs("flatpulse.scrapers.sources.burger", "WARNING") as logs:
            listings = await BurgerScraper().fetch_listings()

        self.assertIn("geneve-studio-meuble", logs.output[0])
        self.assertEqual(len(listings), 3)
