"""Unit tests for the scrapers base class."""

import unittest
from typing import Any
from unittest.mock import AsyncMock, patch

from parsel import Selector

from flatpulse.common.utils import parse_swiss_price
from flatpulse.scrapers.base import (
    OPTIONAL_FIELDS,
    AbstractScraper,
    HttpScraper,
)
from tests.contract.test_scraper_contract import ScraperContractMixin
from tests.helpers import response_from_fixture


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
            "price_chf": parse_swiss_price(node.css("span.price::text").get()),
        }


class TestMinimalScraperContract(
    ScraperContractMixin, unittest.IsolatedAsyncioTestCase
):
    """MinimalScraper honours the shared scraper contract."""

    scraper_class = MinimalScraper
    fixture_name = "same_listing.html"


class TestHttpScraper(unittest.IsolatedAsyncioTestCase):
    """Unit tests for the HttpScraper class."""

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    async def test_fetch_returns_list_of_dicts_with_required_keys(
        self, mock_get: AsyncMock
    ) -> None:
        """Test that fetch_listings returns a list of dicts with the required keys."""
        mock_get.return_value = response_from_fixture("sample_listing.html")

        scraper = MinimalScraper()
        result = await scraper.fetch_listings()

        mock_get.assert_awaited_once()
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 3)
        for listing in result:
            self.assertIsInstance(listing, dict)
            self.assertIsNotNone(listing["external_id"])
            self.assertTrue(listing["external_url"].startswith("http"))
            self.assertIsNotNone(listing["title"])

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    async def test_missing_price_returns_none(self, mock_get: AsyncMock) -> None:
        """Test that listings with missing or non-numeric prices return None for price_chf and do not crashes."""
        mock_get.return_value = response_from_fixture("listing_no_price.html")

        scraper = MinimalScraper()
        result = await scraper.fetch_listings()

        for listing in result:
            self.assertIsNone(listing["price_chf"])

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    async def test_fingerprint_deterministic(self, mock_get: AsyncMock) -> None:
        """Test that the fingerprint method returns the same value for the same input."""
        mock_get.return_value = response_from_fixture("same_listing.html")

        scraper = MinimalScraper()
        result = await scraper.fetch_listings()
        self.assertEqual(result[0]["fingerprint"], result[1]["fingerprint"])

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    async def test_fingerprint_changes_on_price_change(
        self, mock_get: AsyncMock
    ) -> None:
        """Test that the fingerprint method returns different values when the price changes."""
        mock_get.return_value = response_from_fixture("different_price.html")

        scraper = MinimalScraper()
        result = await scraper.fetch_listings()
        self.assertNotEqual(result[0]["fingerprint"], result[1]["fingerprint"])


class TestScraperContract(unittest.TestCase):
    """Tests for the abstract contract and dict building."""

    def test_abstract_classes_cannot_be_instantiated(self) -> None:
        """AbstractScraper and HttpScraper are abstract and must not be instantiable."""
        with self.assertRaises(TypeError):
            AbstractScraper()  # type: ignore[abstract]
        with self.assertRaises(TypeError):
            HttpScraper()  # type: ignore[abstract]

    def test_missing_optional_fields_become_none(self) -> None:
        """Optional fields omitted by parse_listing are filled with None."""
        listing = MinimalScraper()._build_listing(
            {
                "external_id": "1",
                "external_url": "https://example.com/a",
                "title": "Flat A",
            }
        )
        for field in OPTIONAL_FIELDS:
            self.assertIsNone(listing[field])

    def test_missing_required_field_raises(self) -> None:
        """A missing required field must fail loudly."""
        with self.assertRaises(KeyError):
            MinimalScraper()._build_listing({"external_id": "1", "title": "Flat A"})
