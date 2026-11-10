"""Unit tests for the Naef Immobilier scraper."""

import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from parsel import Selector

from flatpulse.common.models import PropertyType
from flatpulse.scrapers.rate_limiter import RateLimiter
from flatpulse.scrapers.sources.naef import NaefScraper
from tests.contract.test_scraper_contract import ScraperContractMixin
from tests.helpers import CANTON_LOOKUP, response_from_fixture


class TestNaefScraper(ScraperContractMixin, unittest.IsolatedAsyncioTestCase):
    """Contract tests and named cases of NaefScraper.

    `naef_cases.json` holds named cases captured on 30.10.2026, 03.11.2026 and
    08.11.2026, unchanged from the catalogue.
    """

    scraper_class = NaefScraper
    fixture_name = "naef_cases.json"

    def new_scraper(self) -> NaefScraper:
        """A fresh NaefScraper, typed as such: some cases call its parse_listing."""
        return NaefScraper(
            rate_limiter=AsyncMock(spec=RateLimiter), canton_lookup=CANTON_LOOKUP
        )

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

    async def test_naef_canton_from_postal_code_when_empty(self) -> None:
        """An empty `adresse_canton` is read from the postal code, and its town."""
        cases = {
            "214177.1113": "VD",  # 1070 Puidoux
            "276209.1": "NE",  # 2300 La Chaux-de-Fonds
            "EC.47365": "GE",  # 1290 Versoix, a code shared with Vaud
        }
        for external_id, canton in cases.items():
            with self.subTest(external_id=external_id):
                await self.assert_listing(external_id, {"canton": canton})

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
                self.new_scraper().parse_listing(node)

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    async def test_naef_invalid_prop_is_skipped(self, mock_get: AsyncMock) -> None:
        """A prop Listing rejects is logged and skipped; the other props come out."""
        payload = json.loads(response_from_fixture(self.fixture_name).text)
        payload["props"][0]["link"] = "/location/relative/"
        mock_get.return_value = MagicMock(text=json.dumps(payload))

        with self.assertLogs("flatpulse.scrapers.base", "WARNING") as captured:
            listings = await self.new_scraper().fetch_listings()

        self.assertEqual(len(listings), len(payload["props"]) - 1)
        [warning] = captured.output
        self.assertIn("external_url", warning)

    def test_naef_net_above_gross_has_no_charges(self) -> None:
        """Charges exist only when gross > net: a reversed pair gives None, not abs()."""
        payload = json.loads(response_from_fixture(self.fixture_name).text)
        prop = next(p for p in payload["props"] if p["no_dossier"] == "261036.6001")
        prop = {**prop, "loyer_mensuel_brut": 1800, "loyer_mensuel_net": 2000}

        listing = self.new_scraper().parse_listing(Selector(text=json.dumps(prop)))

        self.assertIsNone(listing.charges_chf)

    def test_naef_unknown_type_code_is_logged_with_its_id(self) -> None:
        """A new Naef type code gives None and a WARNING naming the listing."""
        payload = json.loads(response_from_fixture(self.fixture_name).text)
        prop = next(p for p in payload["props"] if p["no_dossier"] == "261036.6001")
        node = Selector(text=json.dumps({**prop, "type_code": "XYZ"}))

        with self.assertLogs("flatpulse.scrapers.sources.naef", "WARNING") as logs:
            listing = self.new_scraper().parse_listing(node)

        self.assertIsNone(listing.property_type)
        self.assertIn("XYZ", logs.output[0])
        self.assertIn("261036.6001", logs.output[0])

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
        """Parking, commercial premises and houses keep their exact property types."""
        await self.assert_listing(
            "201402.61105", {"property_type": PropertyType.PARKING}
        )
        await self.assert_listing(
            "214177.1113", {"property_type": PropertyType.COMMERCIAL}
        )
        await self.assert_listing("CP.19643", {"property_type": PropertyType.HOUSE})

    async def test_naef_keeps_other_cantons(self) -> None:
        """A Valais listing keeps the VS canton abbreviation."""
        await self.assert_listing("CP.19643", {"canton": "VS"})

    async def test_naef_keeps_every_fixture_property(self) -> None:
        """Every property in the fixture is returned exactly once."""
        payload = json.loads(response_from_fixture(self.fixture_name).text)
        results = await self.fetch_from_fixture()
        expected_ids = {prop["no_dossier"] for prop in payload["props"]}

        self.assertEqual(len(results), len(payload["props"]))
        self.assertEqual({listing.external_id for listing in results}, expected_ids)

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
