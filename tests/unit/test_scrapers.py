"""Unit tests for the scrapers base class."""

import unittest
from pathlib import Path
from pprint import pprint
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from parsel import Selector

from flatpulse.scrapers.base import HttpScraper

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


class MinimalScraper(HttpScraper):
    """Smallest possible HttpScraper subclass, used only to exercise the base class."""

    base_url = "https://example.com/louer"

    def listing_nodes(self, page: Selector) -> list[Selector]:
        return page.css("div.listing")

    def parse_listing(self, node: Selector) -> dict[str, Any]:
        return {
            "external_id": node.attrib.get("data-id"),
            "external_url": node.css("a.title::attr(href)").get(),
            "title": node.css("a.title::text").get(),
            "price_chf": self.parse_price_chf(node.css("span.price::text").get()),
        }


class TestHttpScraper(unittest.IsolatedAsyncioTestCase):
    """Unit tests for the HttpScraper class."""

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    async def test_fetch_returns_list_of_dicts_with_required_keys(
        self, mock_get: AsyncMock
    ) -> None:
        # 1. Préparer ce que le "faux" GET doit renvoyer
        html = (FIXTURES_DIR / "sample_listing.html").read_text(encoding="utf-8")
        fake_response = MagicMock()
        fake_response.text = html
        fake_response.raise_for_status = MagicMock()  # ne lève rien
        mock_get.return_value = fake_response

        # 2. Exécuter le code réel, qui croit parler à un vrai serveur
        scraper = MinimalScraper()
        result = await scraper.fetch_listings()

        mock_get.assert_awaited_once()  # le scraper a bien appelé .get() une fois
        self.assertIsInstance(result, list)
        pprint(result)
        self.assertEqual(len(result), 3)
        for listing in result:
            self.assertIsInstance(listing, dict)
            self.assertTrue(listing["external_id"])
            self.assertTrue(listing["external_url"].startswith("http"))
            self.assertTrue(listing["title"])
