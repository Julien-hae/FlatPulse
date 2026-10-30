"""Unit tests for the Naef Immobilier scraper."""

import unittest
from typing import Any
from unittest.mock import AsyncMock, patch

from flatpulse.scrapers.base import REQUIRED_FIELDS
from flatpulse.scrapers.sources.naef import NaefScraper
from tests.contract.test_scraper_contract import ScraperContractMixin
from tests.helpers import response_from_fixture

IMAGES = "https://www.naef.ch/files/location/images/s_listing_page/"


class TestNaefScraper(ScraperContractMixin, unittest.IsolatedAsyncioTestCase):
    """Contract and unit tests for NaefScraper.

    The fixture is the whole `get_all_props` payload of 30.10.2026 (963 properties).
    """

    scraper_class = NaefScraper
    fixture_name = "naef_location.json"

    async def listing(self, external_id: str) -> dict[str, Any]:
        """Return the fixture listing whose external_id matches."""
        listings = await self.fetch_from_fixture()
        return next(item for item in listings if item["external_id"] == external_id)

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    async def test_parse_naef_fixture(self, mock_get: AsyncMock) -> None:
        """fetch_listings turns every property of the payload into a listing."""
        mock_get.return_value = response_from_fixture(self.fixture_name)

        result = await NaefScraper().fetch_listings()

        self.assertEqual(len(result), 963)
        for item in result:
            self.assertIsInstance(item, dict)
            for field in REQUIRED_FIELDS:
                self.assertIn(field, item)
                self.assertTrue(item[field])
            self.assertIsInstance(item["price_chf"], (int, type(None)))
            self.assertIsInstance(item["nb_rooms"], (float, type(None)))
            self.assertIsInstance(item["surface_m2"], (float, type(None)))

    async def test_every_property_has_a_distinct_id(self) -> None:
        """No two properties of the payload share a no_dossier."""
        listings = await self.fetch_from_fixture()

        ids = [item["external_id"] for item in listings]
        self.assertEqual(len(set(ids)), len(ids))

    async def test_apartment_property(self) -> None:
        """Every field of a Geneva apartment is extracted."""
        item = await self.listing("216923.1")

        self.assertEqual(item["title"], "Appartement")
        self.assertEqual(
            item["external_url"],
            "https://www.naef.ch/location/appartement/1201/rue-de-zurich-3-a-geneve/216923.1/",
        )
        self.assertEqual(item["price_chf"], 604400)
        self.assertEqual(item["nb_rooms"], 5.5)
        self.assertEqual(item["surface_m2"], 134.0)
        self.assertEqual(item["city"], "Genève")
        self.assertEqual(len(item["images"]), 7)
        self.assertEqual(
            item["images"][0], f"{IMAGES}216923.1_photo1179645_22052026.jpg"
        )

    async def test_rent_with_centimes(self) -> None:
        """'162.15' is CHF 162.15, i.e. 16215 centimes."""
        item = await self.listing("213250.61006")

        self.assertEqual(item["price_chf"], 16215)

    async def test_price_on_request_is_none(self) -> None:
        """loyer_sur_demande 'oui' wins over the loyer_mensuel_brut sent alongside."""
        item = await self.listing("EC.35666")

        self.assertIsNone(item["price_chf"])

    async def test_whole_rooms_and_studio(self) -> None:
        """'3' gives 3.0 rooms and a studio's '1' gives 1.0."""
        whole = await self.listing("EC.37246")
        studio = await self.listing("276361.8005")

        self.assertEqual(whole["nb_rooms"], 3.0)
        self.assertEqual(studio["nb_rooms"], 1.0)

    async def test_zero_rooms_and_surface_are_none(self) -> None:
        """A parking sends nb_pieces 0 and surface_habitable 0: both are unknown."""
        item = await self.listing("201402.61105")

        self.assertIsNone(item["nb_rooms"])
        self.assertIsNone(item["surface_m2"])

    async def test_surface_without_unit(self) -> None:
        """surface_habitable is a bare number of m2, decimals included."""
        apartment = await self.listing("216923.1")
        parking = await self.listing("211173.61009")

        self.assertEqual(apartment["surface_m2"], 134.0)
        self.assertEqual(parking["surface_m2"], 2.25)

    async def test_images_sent_as_an_indexed_object(self) -> None:
        """imgs may arrive as {"1": url, "0": url}; images keep the index order."""
        item = await self.listing("223628.2004")

        self.assertEqual(
            item["images"],
            [
                f"{IMAGES}223628.2004_photo1189586_20102026.jpg",
                f"{IMAGES}223628.2004_photo296304_21062024.jpg",
            ],
        )

    async def test_property_without_title_still_has_a_title(self) -> None:
        """Some parkings send an empty intitule_plaquette; the listing still gets a title."""
        item = await self.listing("212528.62211")

        self.assertTrue(item["title"])
