"""Unit tests for the Comptoir Immobilier scraper."""

import unittest
from unittest.mock import AsyncMock, MagicMock, call, patch

import httpx

from flatpulse.common.models import Listing, PropertyType
from flatpulse.scrapers.sources.comptoir import ComptoirScraper
from tests.contract.test_scraper_contract import ScraperContractMixin
from tests.helpers import response_from_fixture

YVORNE = (
    "magnifique-duplex-de-5-5-pices-en-attique-denviron-165m2-dans-un-petit-"
    "immeuble-avec-ascenseur-lavenue-de-lausanne-24-situ-sur-la-commune-dyvorne-"
    "10-minutes-pieds-du-centre-ville-dai"
)
GENEVA = "a-louer-appartement-de-4-pices-au-7me-tage"


def fake_get(url: str) -> MagicMock:
    """Serve the frozen catalogue, and the frozen fiche of each of its cards."""
    if url.startswith(ComptoirScraper.base_url + "?page="):
        return response_from_fixture("comptoir_cases.html")
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    return response_from_fixture(f"comptoir/{slug}.html")


class TestComptoirScraper(ScraperContractMixin, unittest.IsolatedAsyncioTestCase):
    """Contract tests and named cases of ComptoirScraper.

    `comptoir_cases.html` holds nine catalogue cards without pagination;
    `comptoir/` holds their nine fiches of 04.11.2026, contact anonymised.
    """

    scraper_class = ComptoirScraper
    fixture_name = "comptoir_cases.html"

    async def fetch_from_fixture(self) -> list[Listing]:
        """Serve the catalogue, then its fiches, without waiting the crawl-delay."""
        with (
            patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            mock_get.side_effect = fake_get
            return await self.scraper_class().fetch_listings()

    async def test_comptoir_details_table(self) -> None:
        """A Geneva apartment comes out of its « Détails » table, field by field."""
        await self.assert_listing(
            GENEVA,
            {
                "title": "A louer, appartement de 4 pièces au 7ème étage",
                "property_type": PropertyType.APARTMENT,
                "price_chf": 276700,
                "charges_chf": 21700,
                "nb_rooms": 4.0,
                "surface_m2": 79.0,
                "floor": 7,
                "address": "Quai Charles-Page 49",
                "city": "Genève",
                "canton": "GE",
            },
        )

    async def test_comptoir_other_canton_is_kept(self) -> None:
        """A Vaud duplex is kept; its floor comes from the table, not the title."""
        await self.assert_listing(
            YVORNE,
            {
                # The site's typographic apostrophes, kept as scraped
                "title": "Magnifique duplex de 5.5 pièces en attique d’environ 165m2 "  # noqa: RUF001
                "dans un petit immeuble avec ascenseur, à l’Avenue de Lausanne 24. "  # noqa: RUF001
                "Situé sur la commune d’Yvorne à 10 minutes à pieds du centre ville d’Ai",  # noqa: RUF001
                "price_chf": 307000,
                "nb_rooms": 5.5,
                "surface_m2": 165.0,
                "floor": 2,
                "address": "Route de Lausanne 24 A",
                "city": "Yvorne",
                "canton": "VD",
            },
        )

    async def test_comptoir_description_and_images(self) -> None:
        """The fiche gives the full description and every photo of its gallery."""
        listing = next(
            item
            for item in await self.fetch_from_fixture()
            if item.external_id == YVORNE
        )

        assert listing.description is not None
        self.assertTrue(listing.description.startswith("Magnifique duplex de 5.5"))
        self.assertTrue(listing.description.endswith("Cuisine équipée, WC séparé."))
        self.assertEqual(len(listing.images), 13)
        self.assertEqual(
            listing.images[0],
            "https://comptoir-immo.ch/external-images/?url=https%3A%2F%2Fmedia.apimo.pro"
            "%2Fcache%2F802522d3f833ead4be77ef2784873b0f_5e7471171f_1024-original.jpg"
            "&propertyId=1006865&preset=fullwidth",
        )

    async def test_comptoir_without_surface(self) -> None:
        """A fiche without a surface row, nor photos, keeps its rooms."""
        await self.assert_listing(
            "appartement-avec-balcon-situ-dans-environnement-verdoyant-proche-de-"
            "toutes-les-commodits",
            {"surface_m2": None, "nb_rooms": 5.0, "images": (), "city": "Carouge"},
        )

    async def test_comptoir_parking(self) -> None:
        """A parking has a rent, no rooms, and lies on the ground floor."""
        await self.assert_listing(
            "emplacement-de-parking-dans-un-parking-scuris-cet-place-est-louer-"
            "uniquement-des-personnes-extrieures-au-plq-amandolier",
            {
                "property_type": PropertyType.PARKING,
                "price_chf": 26000,
                "nb_rooms": None,
                "floor": 0,
            },
        )

    async def test_comptoir_rent_per_square_meter(self) -> None:
        """« CHF 600.- / m² / an » on 117 m² is a monthly rent of CHF 5'850.-."""
        await self.assert_listing(
            "belles-surfaces-administratives-dans-un-immeuble-de-haut-standing-dans-le-"
            "quartier-des-banques",
            {
                "property_type": PropertyType.COMMERCIAL,
                "price_chf": 585000,
                "charges_chf": None,
                "surface_m2": 117.0,
                "floor": 1,
            },
        )

    async def test_comptoir_surface_only_on_fiche(self) -> None:
        """The card shows no surface; the fiche's « Surface utile » prices the m²."""
        await self.assert_listing(
            "cabinet-bureau-remettre-au-centre-de-sion",
            {"surface_m2": 120.0, "price_chf": 308000, "charges_chf": None},
        )

    async def test_comptoir_yearly_rent(self) -> None:
        """« CHF 18'720.- / an » is a monthly rent; yearly charges are not added."""
        await self.assert_listing(
            "bureau-louer-au-centre-de-monthey",
            {"price_chf": 156000, "charges_chf": None, "floor": 0, "canton": "VS"},
        )

    async def test_comptoir_price_on_request_is_none(self) -> None:
        """« Prix sur demande » gives no price, never 0."""
        await self.assert_listing(
            "surface-administrative-dexception-au-coeur-de-genve",
            {"price_chf": None, "surface_m2": 1061.0},
        )

    async def test_comptoir_storage_without_surface(self) -> None:
        """A basement dépôt priced per m² without a surface has no price, never 0."""
        await self.assert_listing(
            "a-louer-dpot-scuris-plainpalais",
            {
                "property_type": PropertyType.STORAGE,
                "price_chf": None,
                "surface_m2": None,
                "floor": -1,
            },
        )

    async def test_comptoir_waits_crawl_delay_before_each_request(self) -> None:
        """Every request, catalogue or fiche, waits the 10 s Crawl-delay of robots.txt."""
        manager = MagicMock()
        with (
            patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            mock_get.side_effect = fake_get
            manager.attach_mock(mock_get, "get")
            manager.attach_mock(mock_sleep, "sleep")
            await self.scraper_class().fetch_listings()

        names = [name for name, _, _ in manager.mock_calls]
        self.assertEqual(names, ["sleep", "get"] * 10)
        self.assertEqual(mock_sleep.await_args_list, [call(10)] * 10)

    async def test_comptoir_failing_fiche_is_skipped(self) -> None:
        """A fiche that fails to download is logged; the other fiches come out."""
        expected = len(await self.fetch_from_fixture()) - 1

        def get(url: str) -> MagicMock:
            if GENEVA in url:
                raise httpx.RemoteProtocolError("Server disconnected")
            return fake_get(url)

        with (
            patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
            patch("asyncio.sleep", new_callable=AsyncMock),
            self.assertLogs("flatpulse.scrapers.sources.comptoir", "WARNING"),
        ):
            mock_get.side_effect = get
            listings = await self.scraper_class().fetch_listings()

        self.assertEqual(len(listings), expected)

    async def test_comptoir_invalid_fiche_is_skipped(self) -> None:
        """A fiche that cannot be parsed is logged and skipped; the others come out."""
        expected = len(await self.fetch_from_fixture()) - 1

        def get(url: str) -> MagicMock:
            response = fake_get(url)
            if GENEVA in url:
                response.text = response.text.replace("<h1", "<h3")
            return response

        with (
            patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
            patch("asyncio.sleep", new_callable=AsyncMock),
            self.assertLogs("flatpulse.scrapers.base", "WARNING"),
        ):
            mock_get.side_effect = get
            listings = await self.scraper_class().fetch_listings()

        self.assertEqual(len(listings), expected)
