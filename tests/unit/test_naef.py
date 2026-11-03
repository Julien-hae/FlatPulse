"""Unit tests for the Naef Immobilier scraper."""

import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from parsel import Selector

from flatpulse.common.models import PropertyType
from flatpulse.config import CANTON_TO_ABR
from flatpulse.scrapers.sources.naef import NaefScraper
from tests.contract.test_scraper_contract import ScraperContractMixin
from tests.helpers import response_from_fixture


class TestNaefScraper(ScraperContractMixin, unittest.IsolatedAsyncioTestCase):
    """Contract tests and named cases of NaefScraper.

    `naef_cases.json` holds named cases captured on 30.10.2026 and 03.11.2026,
    unchanged from the catalogue.
    """

    scraper_class = NaefScraper
    fixture_name = "naef_cases.json"

    async def test_naef_full_apartment(self) -> None:
        """A complete Geneva apartment comes out field by field."""
        await self.assert_listing(
            "261036.6001",
            {
                "title": "Appartement duplex de 6 pièces situé dans le quartier...",
                "price_chf": 455000,
                "nb_rooms": 6.0,
                "city": "Genève",
                "external_url": "https://www.naef.ch/location/appartement/1202/avenue-de-la-foret-5-geneve/261036.6001/",
            },
        )

    async def test_naef_price_on_request_is_none(self) -> None:
        """A rent on request has no price, even when the payload carries a figure."""
        await self.assert_listing("CP.19643", {"price_chf": None})

    async def test_naef_parking(self) -> None:
        """A Geneva parking space keeps its title, rent and town."""
        await self.assert_listing(
            "201402.61105",
            {
                "title": "Place de parc intérieure",
                "price_chf": 18000,
                "city": "Genève",
                "nb_rooms": None,
            },
        )

    async def test_naef_apartment_without_canton(self) -> None:
        """An apartment with an empty canton keeps its town."""
        await self.assert_listing(
            "276209.1",
            {
                "title": "Appartement de 2 pièces entièrement rénové avec ...",
                "price_chf": 93500,
                "nb_rooms": 2.0,
                "city": "La Chaux-de-Fonds",
            },
        )

    async def test_naef_title_falls_back_to_type_designation(self) -> None:
        """A missing brochure title is replaced by the property's designation."""
        await self.assert_listing("212528.62211", {"title": "Garage individuel"})

    async def test_naef_listing_with_indexed_images(self) -> None:
        """`imgs` given as an indexed object does not disturb the other fields."""
        await self.assert_listing(
            "223628.2004",
            {
                "title": "Appartement en cours de rénovation",
                "price_chf": 207000,
                "nb_rooms": 3.5,
                "city": "Lausanne",
            },
        )

    def test_naef_missing_required_field_is_a_value_error(self) -> None:
        """No link, id or title is an invalid listing (ValueError), not a crash."""
        payload = json.loads(response_from_fixture(self.fixture_name).text)
        for key in ("link", "no_dossier", "intitule_plaquette"):
            prop = {**payload["props"][0], key: None, "type_designation_fr": None}
            node = Selector(text=json.dumps(prop))
            with self.subTest(key=key), self.assertRaises(ValueError):
                NaefScraper().parse_listing(node)

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    async def test_naef_invalid_prop_is_skipped(self, mock_get: AsyncMock) -> None:
        """A prop Listing rejects is logged and skipped; the other props come out."""
        payload = json.loads(response_from_fixture(self.fixture_name).text)
        payload["props"][0]["link"] = "/location/relative/"
        mock_get.return_value = MagicMock(text=json.dumps(payload))

        with self.assertLogs("flatpulse.scrapers.base", "WARNING") as captured:
            listings = await NaefScraper().fetch_listings()

        self.assertEqual(len(listings), len(payload["props"]) - 1)
        [warning] = captured.output
        self.assertIn("external_url", warning)

    async def test_naef_full_apartment_fields(self) -> None:
        """Full apartment fields are parsed correctly."""
        results = await self.fetch_from_fixture()
        listing = next(item for item in results if item.external_id == "261036.6001")
        self.assertIsNotNone(listing)
        self.assertEqual(
            listing.title, "Appartement duplex de 6 pièces situé dans le quartier..."
        )
        self.assertEqual(listing.price_chf, 455000)
        self.assertEqual(listing.nb_rooms, 6.0)
        self.assertEqual(listing.city, "Genève")
        self.assertEqual(listing.property_type, PropertyType.APARTMENT)
        self.assertEqual(listing.surface_m2, 119)
        self.assertEqual(listing.postal_code, "1202")
        self.assertEqual(listing.canton, "GE")
        self.assertEqual(listing.charges_chf, 55000)
        self.assertEqual(
            listing.external_url,
            "https://www.naef.ch/location/appartement/1202/avenue-de-la-foret-5-geneve/261036.6001/",
        )

    async def test_naef_keeps_every_property_type(self) -> None:
        """All property types are recognized."""
        results = await self.fetch_from_fixture()
        types = {item.property_type for item in results}
        self.assertIn(PropertyType.APARTMENT, types)
        self.assertIn(PropertyType.HOUSE, types)
        self.assertIn(PropertyType.PARKING, types)
        self.assertIn(PropertyType.COMMERCIAL, types)

    async def test_naef_keeps_other_cantons(self) -> None:
        """Cantons are valid."""
        results = await self.fetch_from_fixture()
        cantons = {item.canton for item in results}
        test_values = set(CANTON_TO_ABR.values()) | {None}
        for abbr in cantons:
            self.assertIn(abbr, test_values)

    async def test_naef_empty_canton_is_none_with_postal_code(self) -> None:
        """Empty cantons have postal codes."""
        results = await self.fetch_from_fixture()
        for item in results:
            if not item.canton:
                self.assertIsNotNone(item.postal_code)
            if not item.postal_code:
                self.assertIsNotNone(item.canton)

    async def test_naef_zero_surface_is_none(self) -> None:
        """A zero surface is absent for parking, commercial and storage listings."""
        for external_id in (
            "201402.61105",
            "268575.61001",
            "275985.1006",
            "218044.61025",
        ):
            with self.subTest(external_id=external_id):
                await self.assert_listing(external_id, {"surface_m2": None})

    async def test_naef_indexed_images(self) -> None:
        """Images are indexed."""
        results = await self.fetch_from_fixture()
        listing = next(item for item in results if item.external_id == "223628.2004")
        self.assertEqual(
            listing.images,
            (
                "https://www.naef.ch/files/location/images/s_listing_page/223628.2004_photo296304_21062024.jpg",
                "https://www.naef.ch/files/location/images/s_listing_page/223628.2004_photo1189586_20102026.jpg",
            ),
        )
