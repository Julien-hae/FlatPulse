"""Unit tests for the Burger Immobilier scraper."""

import re
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from parsel import Selector

from flatpulse.common.models import Listing, PropertyType
from flatpulse.scrapers.sources.burger import BurgerScraper
from tests.contract.test_scraper_contract import ScraperContractMixin
from tests.helpers import response_from_fixture

LOUER = "https://www.burger-sa.ch/fr/louer/"
MONT_BLANC = LOUER + "geneve-magnifique-appartement-de-5-pieces-br-rue-du-mont-bla"
APARTMENT = LOUER + "geneve-appartement-de-3-pieces-au-2eme-etage"


def fake_get(url: str) -> MagicMock:
    """Serve the frozen sitemap, and the frozen fiche of each of its entries."""
    if url == BurgerScraper.base_url:
        return response_from_fixture("burger_sitemap.xml")
    return response_from_fixture(f"burger/{url.removeprefix(LOUER)}.html")


def apartment_with_surface_row(row: str) -> Selector:
    """The 3-room apartment fiche whose « 59 m2 » feature row reads `row` instead."""
    html = fake_get(APARTMENT).text
    return Selector(text=html.replace(">59 m2<", f">{row}<"))


class TestBurgerScraper(ScraperContractMixin, unittest.IsolatedAsyncioTestCase):
    """Contract tests and named cases of BurgerScraper.

    `burger_sitemap.xml` keeps ten `/fr/louer/` entries and one sale fiche from the
    sitemap of 30.10.2026; `burger/` holds the ten rental fiches, contact anonymised.
    """

    scraper_class = BurgerScraper
    fixture_name = "burger_sitemap.xml"

    async def fetch_from_fixture(self) -> list[Listing]:
        """Serve the sitemap, then its rental fiches."""
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = fake_get
            return await self.scraper_class().fetch_listings()

    async def test_burger_apartment_fiche(self) -> None:
        """A complete Geneva apartment fiche comes out field by field."""
        await self.assert_listing(
            LOUER + "geneve-appartement-de-3-pieces-au-2eme-etage",
            {
                "title": "Appartement de 3 pièces au 2ème étage",
                "price_chf": 260000,
                "nb_rooms": 3.0,
                "surface_m2": 59.0,
                "address": "Rue de Contamines 36",
                "city": "Genève",
            },
        )

    async def test_burger_ground_floor_apartment(self) -> None:
        """A ground-floor apartment, whose street has an apostrophe, comes out whole."""
        await self.assert_listing(
            LOUER + "geneve-appartement-de-3-pieces-au-rez-de-chaussee",
            {
                "title": "Appartement de 3 pièces au rez-de-chaussée",
                "price_chf": 260000,
                "nb_rooms": 3.0,
                "surface_m2": 51.0,
                "address": "Rue de l'Athénée 40",
                "city": "Genève",
                "floor": 0,
            },
        )

    async def test_burger_unknown_rooms_is_none(self) -> None:
        """« 0.0 pièces » means the number of rooms is unknown."""
        await self.assert_listing(
            LOUER + "geneve-appartement-de-charme-et-de-prestige", {"nb_rooms": None}
        )

    async def test_burger_studio_has_one_room(self) -> None:
        """A studio counts one room."""
        await self.assert_listing(
            LOUER + "geneve-studio-meuble",
            {
                "title": "Studio meublé",
                "price_chf": 215000,
                "nb_rooms": 1.0,
                "property_type": PropertyType.APARTMENT,
            },
        )

    async def test_burger_arcade_with_yearly_rent(self) -> None:
        """An arcade rented « / année » keeps its surface and address."""
        await self.assert_listing(
            LOUER + "geneve-arcade-a-louer-en-plein-centre-ville",
            {
                "title": "Arcade à louer en plein centre-ville.",
                "nb_rooms": None,
                "surface_m2": 17.0,
                "address": "Boulevard Helvétique 26",
                "city": "Genève",
                "price_chf": 200000,
            },
        )

    async def test_burger_offices_with_rent_per_m2_per_year(self) -> None:
        """Offices rented « / m2 / année » keep their surface and address."""
        await self.assert_listing(
            LOUER + "satigny-bureaux-de-214-m2-a-satignybr",
            {
                "surface_m2": 214.0,
                "address": "Rue des Sablières 1-1bis-3",
                "city": "Satigny",
                "price_chf": 463667,
                "property_type": PropertyType.COMMERCIAL,
                "charges_chf": None,
            },
        )

    async def test_burger_parking(self) -> None:
        """A parking space has a rent, no rooms and no surface."""
        await self.assert_listing(
            LOUER + "le-lignon-parking-interne-au-1er-sous-sol",
            {
                "title": "Parking interne au 1er sous-sol",
                "price_chf": 11900,
                "nb_rooms": None,
                "surface_m2": None,
                "city": "Le Lignon",
            },
        )

    def test_burger_no_charges_without_rent(self) -> None:
        """Charges are a share of price_chf: no rent, no charges either."""
        url = LOUER + "geneve-appartement-de-3-pieces-au-2eme-etage"
        html = response_from_fixture(
            "burger/geneve-appartement-de-3-pieces-au-2eme-etage.html"
        ).text.replace("CHF 2'330.— / mois", "Loyer sur demande")

        listing = BurgerScraper().parse_listing(Selector(text=html), url)

        self.assertIsNone(listing.price_chf)
        self.assertIsNone(listing.charges_chf)

    async def test_burger_price_on_request_is_none(self) -> None:
        """« Loyer sur demande » gives no price, never 0."""
        await self.assert_listing(
            LOUER + "veyrier-veyrierbr-depot-a-louer",
            {
                "title": "Dépôt à louer",
                "price_chf": None,
                "surface_m2": 160.0,
                "property_type": PropertyType.STORAGE,
            },
        )

    def test_burger_fiche_without_title_is_a_value_error(self) -> None:
        """A missing <h1> is an invalid listing (ValueError), not an AttributeError."""
        url = LOUER + "geneve-studio-meuble"
        html = response_from_fixture("burger/geneve-studio-meuble.html").text
        page = Selector(text=re.sub(r"<h1[^>]*>.*?</h1>", "", html, flags=re.S))

        with self.assertRaisesRegex(ValueError, "title"):
            BurgerScraper().parse_listing(page, url)

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    async def test_burger_invalid_fiche_is_skipped(self, mock_get: AsyncMock) -> None:
        """A fiche Listing rejects is logged and skipped; the other fiches come out."""
        studio = LOUER + "geneve-studio-meuble"

        def get(url: str) -> MagicMock:
            """Serve the studio fiche without its <h1>, the others unchanged."""
            if url == studio:
                html = response_from_fixture("burger/geneve-studio-meuble.html").text
                return MagicMock(
                    text=re.sub(r"<h1[^>]*>.*?</h1>", "", html, flags=re.S)
                )
            return fake_get(url)

        mock_get.side_effect = get
        expected = len(await self.fetch_from_fixture()) - 1

        with self.assertLogs("flatpulse.scrapers.base", "WARNING") as captured:
            listings = await BurgerScraper().fetch_listings()

        self.assertEqual(len(listings), expected)
        self.assertNotIn(studio, [listing.external_url for listing in listings])
        [warning] = captured.output
        self.assertIn(studio, warning)

    async def test_burger_shared_url_prefix_gives_two_listings(self) -> None:
        """Two fiches whose URLs share a prefix stay two listings."""
        listings = await self.fetch_from_fixture()

        ids = {
            item.external_id
            for item in listings
            if item.external_id.startswith(MONT_BLANC)
        }

        self.assertEqual(ids, {MONT_BLANC, MONT_BLANC + "-1017-000402"})

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    async def test_burger_only_rental_fiches_are_fetched(
        self, mock_get: AsyncMock
    ) -> None:
        """The sale fiche of the sitemap is never requested."""
        mock_get.side_effect = fake_get

        await BurgerScraper().fetch_listings()

        requested = [call.args[0] for call in mock_get.call_args_list]
        self.assertNotIn(
            "https://www.burger-sa.ch/fr/acheter/duplex-a-bernex", requested
        )

    async def test_burger_property_type_follows_the_feature_label(self) -> None:
        """Each label of the feature row maps to its PropertyType."""
        cases = {
            "geneve-studio-meuble": PropertyType.APARTMENT,
            "geneve-arcade-a-louer-en-plein-centre-ville": PropertyType.COMMERCIAL,
            "satigny-bureaux-de-214-m2-a-satignybr": PropertyType.COMMERCIAL,
            "le-lignon-parking-interne-au-1er-sous-sol": PropertyType.PARKING,
            "veyrier-veyrierbr-depot-a-louer": PropertyType.STORAGE,
        }
        for slug, property_type in cases.items():
            with self.subTest(slug=slug):
                await self.assert_listing(
                    LOUER + slug, {"property_type": property_type}
                )

    def test_burger_surface_formats(self) -> None:
        """An approximate surface keeps its value, a range keeps its lower bound."""
        for row, surface in {"ENV. 60 M2": 60.0, "de 85 M2 à 100 M2": 85.0}.items():
            with self.subTest(row=row):
                listing = BurgerScraper().parse_listing(
                    apartment_with_surface_row(row), APARTMENT
                )
                self.assertEqual(listing.surface_m2, surface)

    def test_burger_unknown_feature_row_is_logged_and_ignored(self) -> None:
        """A feature row out of the known grammar is logged, never guessed at."""
        page = apartment_with_surface_row("Balcon 12 m2 plein sud")

        with self.assertLogs("flatpulse.scrapers.sources.burger", "WARNING") as logs:
            listing = BurgerScraper().parse_listing(page, APARTMENT)

        self.assertIsNone(listing.surface_m2)
        self.assertEqual(listing.nb_rooms, 3.0)
        [warning] = logs.output
        self.assertIn("Balcon 12 m2 plein sud", warning)
        self.assertIn(APARTMENT, warning)

    async def test_burger_apartment_type_floor_and_charges(self) -> None:
        """Check apartment type, floor and charges."""
        await self.assert_listing(
            LOUER + "geneve-appartement-de-3-pieces-au-2eme-etage",
            {
                "property_type": PropertyType.APARTMENT,
                "floor": 2,
                "charges_chf": 27000,
                "price_chf": 260000,
            },
        )

    async def test_burger_basement_parking(self) -> None:
        """A parking « au 1er sous-sol » is on floor -1."""
        await self.assert_listing(
            LOUER + "le-lignon-parking-interne-au-1er-sous-sol",
            {
                "property_type": PropertyType.PARKING,
                "floor": -1,
                "nb_rooms": None,
            },
        )
