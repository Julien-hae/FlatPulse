"""Unit tests for the Naef Immobilier scraper."""

import json
import unittest
from typing import Any

from flatpulse.scrapers.sources.naef import NaefScraper
from tests.contract.test_scraper_contract import ScraperContractMixin, load_fixture


class TestNaefScraper(ScraperContractMixin, unittest.TestCase):
    """Naef-specific tests, on top of the four inherited contracts."""

    def setUp(self) -> None:
        self.scraper = NaefScraper()
        self.fixture = load_fixture("naef_location.json")

    def fetch_payload(self, *props: dict[str, Any]) -> list[dict[str, Any]]:
        """Fetch listings from an inline payload instead of the fixture."""
        self.fixture = json.dumps({"props": list(props)})
        return self.fetch()

    def test_parse_naef_fixture(self) -> None:
        """Selectors and mapping work on the real payload captured during the spike."""
        listings = self.fetch()

        self.assertEqual(len(listings), 4)
        first = listings[0]
        self.assertEqual(first["external_id"], "214053.4406")
        self.assertTrue(first["external_url"].startswith("https://www.naef.ch/"))
        self.assertEqual(first["title"], "Loft spacieux")
        self.assertEqual(first["description"], "Loft spacieux")
        self.assertEqual(first["city"], "Ste-Croix")
        self.assertEqual(first["surface_m2"], 162.0)
        self.assertEqual(len(first["images"]), 5)
        self.assertIsInstance(first["price_chf"], int)

    def test_naef_price_is_in_centimes(self) -> None:
        """The payload gives francs; the scraper stores centimes."""
        prices = {
            listing["external_id"]: listing["price_chf"] for listing in self.fetch()
        }

        self.assertEqual(prices["214053.4406"], 205000)
        self.assertEqual(prices["223628.2004"], 207000)
        self.assertEqual(prices["276209.1"], 119500)

    def test_naef_price_on_request_is_none(self) -> None:
        """A price on request must be None, never 0, even if the payload has a number."""
        listings = {listing["external_id"]: listing for listing in self.fetch()}

        self.assertIsNone(listings["CP.19642"]["price_chf"])

    def test_naef_rooms_are_floats(self) -> None:
        """Rooms are always floats, including whole numbers."""
        rooms = {
            listing["external_id"]: listing["nb_rooms"] for listing in self.fetch()
        }

        self.assertEqual(rooms["214053.4406"], 4.5)
        self.assertEqual(rooms["276209.1"], 2.0)
        self.assertIsInstance(rooms["276209.1"], float)

    def test_naef_images_as_indexed_object(self) -> None:
        """`imgs` may arrive as an object keyed by index instead of a list."""
        listings = self.fetch_payload(
            {
                "no_dossier": "1",
                "link": "https://www.naef.ch/a",
                "intitule_plaquette": "Flat",
                "imgs": {"0": "https://img/a.jpg", "1": "https://img/b.jpg"},
            }
        )

        self.assertEqual(
            listings[0]["images"], ["https://img/a.jpg", "https://img/b.jpg"]
        )

    def test_naef_missing_fields_become_none(self) -> None:
        """An incomplete listing never crashes: absent or empty fields are None."""
        listings = self.fetch_payload(
            {
                "no_dossier": "1",
                "link": "https://www.naef.ch/a",
                "intitule_plaquette": "Flat",
                "nb_pieces": "",
                "loyer_mensuel_brut": "",
                "surface_habitable": "",
            }
        )

        listing = listings[0]
        for field in ("price_chf", "nb_rooms", "surface_m2", "city", "images"):
            self.assertIsNone(listing[field], field)
