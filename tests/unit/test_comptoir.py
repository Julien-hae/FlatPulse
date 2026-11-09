"""Unit tests for the Comptoir Immobilier scraper."""

import unittest
from unittest.mock import AsyncMock, MagicMock, Mock, call, patch

import httpx
from parsel import Selector

from flatpulse.common.models import Listing, PropertyType
from flatpulse.scrapers.rate_limiter import RateLimiter
from flatpulse.scrapers.sources.comptoir import ComptoirScraper
from tests.contract.test_scraper_contract import ScraperContractMixin
from tests.helpers import CANTON_LOOKUP, response_from_fixture

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

    `comptoir_cases.html` holds ten catalogue cards without pagination;
    `comptoir/` holds their ten fiches of 04.11.2026 and 08.11.2026, contact
    anonymised.
    """

    scraper_class = ComptoirScraper
    fixture_name = "comptoir_cases.html"

    async def fetch_from_fixture(self) -> list[Listing]:
        """Serve the catalogue, then its fiches, without waiting the crawl-delay."""
        with (
            patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
        ):
            mock_get.side_effect = fake_get
            return await self.new_scraper().fetch_listings()

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

    async def test_comptoir_untitled_fiche_takes_property_type(self) -> None:
        """A parking published with an empty <h1> is titled by its « Type de bien »."""
        await self.assert_listing(
            "901969",
            {
                "title": "Parking",
                "property_type": PropertyType.PARKING,
                "price_chf": 20000,
                "floor": -2,
                "address": "Rue du Fort-Barreau 15",
                "city": "Genève",
                "canton": "GE",
                "postal_code": None,
            },
        )

    def test_comptoir_zero_rent_is_none(self) -> None:
        """« CHF 0.- / mois » is no price, never 0: the untitled Satigny parking.

        `comptoir/279533.html` is a fiche without its catalogue card, parsed alone.
        """
        fiche = Selector(text=response_from_fixture("comptoir/279533.html").text)

        listing = self.new_scraper().parse_listing(fiche)

        self.assertEqual(listing.title, "Parking")
        self.assertIsNone(listing.price_chf)
        self.assertEqual(listing.city, "Satigny")
        self.assertEqual(listing.canton, "GE")

    def test_comptoir_no_charges_without_rent(self) -> None:
        """Charges belong to a rent: « CHF 0.- / mois » is no rent, so no charges."""
        html = response_from_fixture("comptoir/279533.html").text.replace(
            "</table>",
            "<tr><th>Charges</th><td>CHF 150.-</td></tr></table>",
            1,
        )

        listing = self.new_scraper().parse_listing(Selector(text=html))

        self.assertIsNone(listing.price_chf)
        self.assertIsNone(listing.charges_chf)

    async def test_comptoir_fiche_without_h1_is_skipped(self) -> None:
        """Only an empty <h1> falls back on the type: no <h1> at all means a redesign.

        Titling such fiches by their type would hide it from the live audit (#119),
        which counts the listings skipped as invalid.
        """
        expected = len(await self.fetch_from_fixture()) - 1

        def get(url: str) -> MagicMock:
            response = fake_get(url)
            if GENEVA in url:
                response.text = response.text.replace("<h1", "<h3")
            return response

        with (
            patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
            self.assertLogs("flatpulse.scrapers.base", "WARNING") as logs,
        ):
            mock_get.side_effect = get
            listings = await self.new_scraper().fetch_listings()

        self.assertEqual(len(listings), expected)
        self.assertIn("title", logs.output[0])

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

    async def test_comptoir_failing_fiche_is_skipped(self) -> None:
        """A fiche that fails to download is logged; the other fiches come out."""
        expected = len(await self.fetch_from_fixture()) - 1

        def get(url: str) -> MagicMock:
            if GENEVA in url:
                raise httpx.RemoteProtocolError("Server disconnected")
            return fake_get(url)

        with (
            patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
            self.assertLogs("flatpulse.scrapers.sources.comptoir", "WARNING"),
        ):
            mock_get.side_effect = get
            listings = await self.new_scraper().fetch_listings()

        self.assertEqual(len(listings), expected)

    async def test_comptoir_invalid_fiche_is_skipped(self) -> None:
        """A fiche that cannot be parsed is logged and skipped; the others come out."""
        expected = len(await self.fetch_from_fixture()) - 1

        def get(url: str) -> MagicMock:
            response = fake_get(url)
            if GENEVA in url:
                # No canonical link, no URL: Listing rejects the fiche.
                response.text = response.text.replace('rel="canonical"', 'rel="x"')
            return response

        with (
            patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
            self.assertLogs("flatpulse.scrapers.base", "WARNING"),
        ):
            mock_get.side_effect = get
            listings = await self.new_scraper().fetch_listings()

        self.assertEqual(len(listings), expected)

    async def test_comptoir_acquires_before_each_page(self) -> None:
        """Each catalogue page acquires a token immediately before its GET."""
        rate_limiter = AsyncMock(spec=RateLimiter)
        scraper = ComptoirScraper(
            rate_limiter=rate_limiter, canton_lookup=CANTON_LOOKUP
        )
        manager = Mock()
        with (
            patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
        ):
            mock_get.return_value = httpx.Response(
                200,
                request=httpx.Request("GET", ComptoirScraper.base_url),
                text=(
                    '<a class="page-number page-numbers">1</a>'
                    '<a class="page-number page-numbers">3</a>'
                ),
            )
            manager.attach_mock(rate_limiter.acquire, "acquire")
            manager.attach_mock(mock_get, "get")
            await scraper.fetch_listings()

        self.assertEqual(
            manager.mock_calls,
            [
                call.acquire("comptoir"),
                call.get(f"{ComptoirScraper.base_url}?page=1"),
                call.acquire("comptoir"),
                call.get(f"{ComptoirScraper.base_url}?page=2"),
                call.acquire("comptoir"),
                call.get(f"{ComptoirScraper.base_url}?page=3"),
            ],
        )
