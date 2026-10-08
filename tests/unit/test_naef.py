"""Unit tests for the Naef Immobilier scraper."""

import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from parsel import Selector

from flatpulse.scrapers.base import (
    REQUIRED_FIELDS,
)
from flatpulse.scrapers.sources.naef import (
    NaefScraper,
)
from tests.unit.test_scrapers import FIXTURES_DIR


class TestNaefScraper(unittest.IsolatedAsyncioTestCase):
    """Unit tests for NaefScraper against the frozen Naef JSON fixture."""

    @staticmethod
    def response_from_fixture(filename: str) -> MagicMock:
        """Build a fake httpx response whose body is the given fixture file."""
        response = MagicMock()
        response.text = (FIXTURES_DIR / filename).read_text(encoding="utf-8")
        response.raise_for_status.return_value = None
        return response

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    async def test_parse_naef_fixture(self, mock_get: AsyncMock) -> None:
        """fetch_listings turns the fixture into listings with the required fields."""
        mock_get.return_value = self.response_from_fixture("naef_location.json")

        result = await NaefScraper().fetch_listings()

        self.assertGreaterEqual(len(result), 2)
        for item in result:
            self.assertIsInstance(item, dict)
            for field in REQUIRED_FIELDS:
                self.assertIn(field, item)
                self.assertTrue(item[field])
            self.assertIsInstance(item["price_chf"], (int, type(None)))
            self.assertIsInstance(item["nb_rooms"], float)

    def test_naef_price_format(self) -> None:
        """Verify Naef rents are converted from CHF to centimes."""
        page = Selector(
            text=json.dumps(
                {
                    "props": [
                        {
                            "no_dossier": "naef-1",
                            "link": "https://www.naef.ch/listing/naef-1",
                            "intitule_plaquette": "Appartement à Genève",
                            "loyer_mensuel_brut": "CHF 1'850.–/mois",  # noqa: RUF001
                        },
                        {
                            "no_dossier": "naef-2",
                            "link": "https://www.naef.ch/listing/naef-2",
                            "intitule_plaquette": "Appartement à Carouge",
                            "loyer_mensuel_brut": "CHF 2'400.–/mois",  # noqa: RUF001
                        },
                    ]
                }
            )
        )
        scraper = NaefScraper()
        listings = [scraper.parse_listing(node) for node in scraper.listing_nodes(page)]

        self.assertEqual(
            [listing["price_chf"] for listing in listings], [185000, 240000]
        )

    def test_naef_rooms_half_and_whole(self) -> None:
        """Verify Naef room counts with half rooms and whole rooms are correctly parsed."""
        page = Selector(
            text=json.dumps(
                {
                    "props": [
                        {
                            "no_dossier": "naef-1",
                            "link": "https://www.naef.ch/listing/naef-1",
                            "intitule_plaquette": "Appartement à Genève",
                            "nb_pieces": "3½ pièces",
                        },
                        {
                            "no_dossier": "naef-2",
                            "link": "https://www.naef.ch/listing/naef-2",
                            "intitule_plaquette": "Appartement à Carouge",
                            "nb_pieces": "4 pièces",
                        },
                    ]
                }
            )
        )
        scraper = NaefScraper()
        listings = [scraper.parse_listing(node) for node in scraper.listing_nodes(page)]
        self.assertEqual([listing["nb_rooms"] for listing in listings], [3.5, 4.0])
