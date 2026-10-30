"""Unit tests for the Burger Immobilier scraper."""

import unittest
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from parsel import Selector

from flatpulse.scrapers.base import REQUIRED_FIELDS
from flatpulse.scrapers.sources.burger import BurgerScraper
from tests.contract.test_scraper_contract import ScraperContractMixin
from tests.helpers import response_from_fixture

LOUER = "https://www.burger-sa.ch/fr/louer/"
URL = f"{LOUER}geneve-appartement-de-charme-et-de-prestige"


def fake_get(url: str) -> MagicMock:
    """Serve the frozen sitemap, and the frozen fiche of each of its entries."""
    if url == BurgerScraper.base_url:
        return response_from_fixture("burger_sitemap.xml")
    return response_from_fixture(f"burger/{url.removeprefix(LOUER)}.html")


class TestBurgerScraper(ScraperContractMixin, unittest.IsolatedAsyncioTestCase):
    """Contract and unit tests for BurgerScraper.

    The fixtures are the sitemap of 30.10.2026 and each of its 42 rental fiches
    (`tests/fixtures/burger/<slug>.html`, contact anonymised).
    """

    scraper_class = BurgerScraper
    fixture_name = "burger_sitemap.xml"

    async def fetch_from_fixture(self) -> list[dict[str, Any]]:
        """Serve the sitemap, then its rental fiches."""
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = fake_get
            return await self.scraper_class().fetch_listings()

    async def listing(self, slug: str) -> dict[str, Any]:
        """Return the fixture listing of the fiche /fr/louer/<slug>."""
        listings = await self.fetch_from_fixture()
        return next(item for item in listings if item["external_id"] == LOUER + slug)

    async def test_parse_burger_fixture(self) -> None:
        """Every rental fiche of the sitemap becomes a listing."""
        result = await self.fetch_from_fixture()

        self.assertEqual(len(result), 42)
        for item in result:
            for field in REQUIRED_FIELDS:
                self.assertTrue(item[field], field)
            self.assertIsInstance(item["price_chf"], (int, type(None)))
            self.assertIsInstance(item["nb_rooms"], (float, type(None)))
            self.assertIsInstance(item["surface_m2"], (float, type(None)))

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    async def test_only_rental_fiches_are_downloaded(self, mock_get: AsyncMock) -> None:
        """/fr/louer itself and the /fr/acheter/ fiches of the sitemap are skipped."""
        mock_get.side_effect = fake_get

        await BurgerScraper().fetch_listings()

        fiches = [args.args[0] for args in mock_get.await_args_list[1:]]
        self.assertEqual(len(fiches), 42)
        for url in fiches:
            self.assertTrue(url.startswith(LOUER), url)

    async def test_fiches_sharing_a_prefix_keep_distinct_ids(self) -> None:
        """Two Mont-Blanc fiches only differ after '…mont-bla': ids stay distinct."""
        listings = await self.fetch_from_fixture()

        ids = [item["external_id"] for item in listings]
        self.assertEqual(len(set(ids)), len(ids))
        self.assertIn(
            f"{LOUER}geneve-magnifique-appartement-de-5-pieces-br-rue-du-mont-bla", ids
        )
        self.assertIn(
            f"{LOUER}geneve-magnifique-appartement-de-5-pieces-br-rue-du-mont-bla"
            "-1017-000402",
            ids,
        )

    async def test_apartment_fiche(self) -> None:
        """Every field of a fiche is read; "0.0 pièces" means an unknown count."""
        listing = await self.listing("geneve-appartement-de-charme-et-de-prestige")

        self.assertEqual(listing["external_url"], URL)
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

    async def test_rooms_come_from_the_metadata_not_the_slug(self) -> None:
        """The '35-pieces' slug and the '3,5 pièces' title lose to 'Appartement 3.0'."""
        carouge = await self.listing(
            "carouge-magnifique-appartement-de-35-pieces-dans-les-combles"
        )
        studio = await self.listing("geneve-studio-meuble")

        self.assertEqual(carouge["nb_rooms"], 3.0)
        self.assertEqual(studio["nb_rooms"], 1.0)

    async def test_fiche_without_surface(self) -> None:
        """A villa whose metadata has no m2 line has no surface."""
        listing = await self.listing("thonex-villa-a-thonex-chemin-de-la-pommeraie-3")

        self.assertIsNone(listing["surface_m2"])
        self.assertEqual(listing["nb_rooms"], 5.0)

    async def test_monthly_rent_formats(self) -> None:
        """Em dash ('CHF 2'350.— / mois') and plain dash ('CHF 400.- / mois')."""
        apartment = await self.listing(
            "geneve-appartement-de-3-pieces-au-3eme-etage-3539-000301"
        )
        parking = await self.listing("places-de-parking-a-louer")

        self.assertEqual(apartment["price_chf"], 235000)
        self.assertEqual(parking["price_chf"], 40000)

    async def test_rent_on_request_is_none(self) -> None:
        """'Loyer sur demande' gives None, never 0."""
        listing = await self.listing("veyrier-veyrierbr-depot-a-louer")

        self.assertIsNone(listing["price_chf"])

    async def test_yearly_price_per_m2_is_not_a_monthly_rent(self) -> None:
        """'CHF 1'000.— / m2 / année' is not stored as a CHF 1'000 monthly rent."""
        listing = await self.listing("geneve-arcade-commerciale-sur-deux-niveaux")

        self.assertIsNone(listing["price_chf"])

    async def test_yearly_rent_is_stored_monthly(self) -> None:
        """'CHF 24'000.— / année' is CHF 2'000 a month."""
        listing = await self.listing("geneve-arcade-a-louer-en-plein-centre-ville")

        self.assertEqual(listing["price_chf"], 200000)

    async def test_fiche_without_photos_has_no_images(self) -> None:
        """Without a carousel, the "similar listings" pictures are not taken."""
        listing = await self.listing("onex-appartement-de-2-pieces-au-12eme-etage")

        self.assertEqual(listing["images"], [])

    async def test_title_whitespace_is_normalised(self) -> None:
        """Runs of spaces and trailing spaces left by the <h1> are collapsed."""
        mont_blanc = await self.listing(
            "geneve-magnifique-appartement-de-5-pieces-br-rue-du-mont-bla"
        )
        bureau = await self.listing("geneve-bureau-a-louer-a-champel")

        self.assertEqual(
            mont_blanc["title"],
            "Magnifique appartement de 5 pièces rue du Mont-Blanc 17",
        )
        self.assertEqual(bureau["title"], "Bureau à louer à Champel")

    async def test_city_with_several_words(self) -> None:
        """'1219 Le Lignon' gives the city 'Le Lignon'."""
        listing = await self.listing("le-lignon-parking-interne-au-1er-sous-sol")

        self.assertEqual(listing["address"], "Route du Bois-des-Frères 2 - 2 C")
        self.assertEqual(listing["city"], "Le Lignon")

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    async def test_a_failing_fiche_is_skipped(self, mock_get: AsyncMock) -> None:
        """A fiche that cannot be downloaded is logged and does not fail the poll."""

        def get(url: str) -> MagicMock:
            if url == URL:
                raise httpx.ConnectError("Server disconnected")
            return fake_get(url)

        mock_get.side_effect = get
        with self.assertLogs("flatpulse.scrapers.sources.burger", "WARNING"):
            result = await BurgerScraper().fetch_listings()

        self.assertEqual(len(result), 41)
        self.assertNotIn(URL, [item["external_id"] for item in result])

    def test_parse_listing_falls_back_to_the_canonical_url(self) -> None:
        """Called through the base contract, without `url`, the fiche names itself."""
        page = Selector(
            text=response_from_fixture(
                "burger/geneve-appartement-de-charme-et-de-prestige.html"
            ).text
        )

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
