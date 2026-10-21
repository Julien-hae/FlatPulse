"""Unit tests for the Burger Immobilier scraper (sitemap + fiche pages)."""

import re
import unittest
from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from parsel import Selector

from flatpulse.scrapers.sources.burger import BurgerScraper
from tests.contract.test_scraper_contract import ScraperContractMixin
from tests.helpers import response_from_fixture

FICHE = "https://www.burger-sa.ch/fr/louer/"
SITEMAP = response_from_fixture("burger_sitemap.xml").text


def serve(sitemap: str = SITEMAP, down: str = "") -> Callable[[str], MagicMock]:
    """Fake httpx GET: the given sitemap, and each fiche from its frozen fixture.

    The fiche whose slug is `down` fails like the live server did once (21.10.2026).
    """

    def get(url: str) -> MagicMock:
        if down and url == FICHE + down:
            raise httpx.RemoteProtocolError(
                "Server disconnected without sending a response."
            )
        if url == BurgerScraper.sitemap_url:
            return MagicMock(text=sitemap)
        return response_from_fixture(f"burger_fiche_{url.removeprefix(FICHE)}.html")

    return get


def requested(mock_get: AsyncMock) -> list[str]:
    """URLs passed to the mocked httpx GET, in call order."""
    return [call.args[0] for call in mock_get.call_args_list]


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

    async def test_keeps_only_dwellings(self) -> None:
        """The parking fiche is dropped; a site-side "0.0 pièces" becomes None."""
        listings = await self.fetch_from_fixture()

        by_slug = {x["external_url"].removeprefix(FICHE): x for x in listings}
        self.assertEqual(
            sorted(by_slug),
            [
                "3-pieces-a-louer",
                "geneve-appartement-de-charme-et-de-prestige",
                "geneve-studio-meuble",
            ],
        )
        charme = by_slug["geneve-appartement-de-charme-et-de-prestige"]
        self.assertIsNone(charme["nb_rooms"])
        self.assertEqual(charme["price_chf"], 700000)
        self.assertEqual(by_slug["3-pieces-a-louer"]["price_chf"], 232000)

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    async def test_second_poll_only_fetches_changed_fiches(
        self, mock_get: AsyncMock
    ) -> None:
        """Unchanged sitemap: only the sitemap. A new lastmod: only that fiche."""
        scraper = BurgerScraper()
        mock_get.side_effect = serve()
        await scraper.fetch_listings()

        mock_get.reset_mock()
        await scraper.fetch_listings()
        self.assertEqual(requested(mock_get), [BurgerScraper.sitemap_url])

        mock_get.reset_mock()
        mock_get.side_effect = serve(
            SITEMAP.replace(
                "geneve-studio-meuble</loc>\n<lastmod>2026-10-21",
                "geneve-studio-meuble</loc>\n<lastmod>2026-10-22",
            )
        )
        await scraper.fetch_listings()
        self.assertEqual(
            requested(mock_get),
            [BurgerScraper.sitemap_url, FICHE + "geneve-studio-meuble"],
        )

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    async def test_new_fiches_come_before_changed_ones(
        self, mock_get: AsyncMock
    ) -> None:
        """A brand-new fiche is not delayed behind fiches whose lastmod moved."""
        studio = r"<url>\s*<loc>[^<]*geneve-studio-meuble</loc>.*?</url>\s*"
        scraper = BurgerScraper()
        mock_get.side_effect = serve(re.sub(studio, "", SITEMAP, flags=re.S))
        await scraper.fetch_listings()

        mock_get.reset_mock()
        scraper.max_fiches_per_poll = 1
        mock_get.side_effect = serve(SITEMAP.replace("2026-10-21", "2026-10-22"))
        await scraper.fetch_listings()

        self.assertEqual(
            requested(mock_get),
            [BurgerScraper.sitemap_url, FICHE + "geneve-studio-meuble"],
        )

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    async def test_caps_fiches_per_poll(self, mock_get: AsyncMock) -> None:
        """A cold start downloads at most max_fiches_per_poll fiches, the rest next poll."""
        scraper = BurgerScraper()
        scraper.max_fiches_per_poll = 3
        mock_get.side_effect = serve()

        await scraper.fetch_listings()
        self.assertEqual(len(requested(mock_get)), 1 + 3)

        mock_get.reset_mock()
        listings = await scraper.fetch_listings()
        self.assertEqual(len(requested(mock_get)), 1 + 1)
        self.assertEqual(len(listings), 3)

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    async def test_drops_fiches_removed_from_sitemap(self, mock_get: AsyncMock) -> None:
        """A fiche that leaves the sitemap is no longer returned."""
        scraper = BurgerScraper()
        mock_get.side_effect = serve()
        await scraper.fetch_listings()

        mock_get.side_effect = serve(
            re.sub(
                r"<url>\s*<loc>[^<]*geneve-studio-meuble</loc>.*?</url>\s*",
                "",
                SITEMAP,
                flags=re.S,
            )
        )
        listings = await scraper.fetch_listings()

        self.assertNotIn(
            FICHE + "geneve-studio-meuble", [x["external_url"] for x in listings]
        )

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    async def test_a_failing_fiche_is_retried_next_poll(
        self, mock_get: AsyncMock
    ) -> None:
        """One fiche failing does not fail the poll: it is logged and retried later."""
        scraper = BurgerScraper()
        mock_get.side_effect = serve(down="geneve-studio-meuble")

        with self.assertLogs("flatpulse.scrapers.sources.burger", "WARNING"):
            listings = await scraper.fetch_listings()
        self.assertEqual(len(listings), 2)

        mock_get.reset_mock()
        mock_get.side_effect = serve()
        listings = await scraper.fetch_listings()
        self.assertEqual(
            requested(mock_get),
            [BurgerScraper.sitemap_url, FICHE + "geneve-studio-meuble"],
        )
        self.assertEqual(len(listings), 3)

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    async def test_a_sitemap_without_fiches_is_an_error(
        self, mock_get: AsyncMock
    ) -> None:
        """A sitemap format change must not pass for "Burger has nothing to rent"."""
        mock_get.side_effect = serve(SITEMAP.replace("/fr/louer/", "/fr/rent/"))

        with self.assertRaises(ValueError):
            await BurgerScraper().fetch_listings()

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    async def test_an_unreadable_fiche_is_logged_and_retried(
        self, mock_get: AsyncMock
    ) -> None:
        """A fiche without its rent block is a markup change, not a non-dwelling."""
        fiches = serve()

        def get(url: str) -> MagicMock:
            if url == FICHE + "geneve-studio-meuble":
                return MagicMock(
                    text="<html><body><h1>Studio meublé</h1></body></html>"
                )
            return fiches(url)

        scraper = BurgerScraper()
        mock_get.side_effect = get
        with self.assertLogs("flatpulse.scrapers.sources.burger", "WARNING") as logs:
            listings = await scraper.fetch_listings()
        self.assertIn("geneve-studio-meuble", logs.output[0])
        self.assertEqual(len(listings), 2)

        mock_get.reset_mock()
        mock_get.side_effect = fiches
        listings = await scraper.fetch_listings()
        self.assertEqual(
            requested(mock_get),
            [BurgerScraper.sitemap_url, FICHE + "geneve-studio-meuble"],
        )
        self.assertEqual(len(listings), 3)
