"""Unit tests for the Naef Immobilier scraper."""

import unittest

from flatpulse.scrapers.sources.naef import NaefScraper
from tests.contract.test_scraper_contract import ScraperContractMixin


class TestNaefScraper(ScraperContractMixin, unittest.IsolatedAsyncioTestCase):
    """Contract tests and named cases of NaefScraper.

    `naef_cases.json` holds seven props taken unchanged from the catalogue of
    30.10.2026, one per trap of the payload.
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

    async def test_naef_office_without_canton(self) -> None:
        """An office with an empty canton and a rent on request is still listed."""
        await self.assert_listing(
            "214177.1113",
            {"title": "Bureau", "price_chf": None, "city": "Puidoux"},
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
