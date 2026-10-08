"""Invariants every HTTP scraper must satisfy, inherited by each scraper's test."""

import unittest
from typing import Any
from unittest.mock import AsyncMock, patch

from flatpulse.scrapers.base import REQUIRED_FIELDS, HttpScraper
from tests.helpers import response_from_fixture


class ScraperContractMixin:
    """Four contract tests shared by every scraper.

    Combine with `unittest.IsolatedAsyncioTestCase` and set `scraper_class` and
    `fixture_name`; the scraper then runs against the frozen fixture, never the network.
    """

    scraper_class: type[HttpScraper]
    fixture_name: str

    async def fetch_from_fixture(self) -> list[dict[str, Any]]:
        """Run a fresh scraper against the frozen fixture."""
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = response_from_fixture(self.fixture_name)
            return await self.scraper_class().fetch_listings()

    async def test_contract_returns_list(self) -> None:
        """fetch_listings returns a list of dicts."""
        result = await self.fetch_from_fixture()
        assert isinstance(self, unittest.TestCase)
        self.assertIsInstance(result, list)
        for listing in result:
            self.assertIsInstance(listing, dict)

    async def test_contract_required_fields(self) -> None:
        """Required fields are non-empty and external_url is absolute."""
        result = await self.fetch_from_fixture()
        assert isinstance(self, unittest.TestCase)
        for listing in result:
            for field in REQUIRED_FIELDS:
                self.assertTrue(listing.get(field), field)
            self.assertTrue(listing["external_url"].startswith("http"))

    async def test_contract_has_fingerprint(self) -> None:
        """Each listing carries a 64-character hex SHA-256 fingerprint."""
        result = await self.fetch_from_fixture()
        assert isinstance(self, unittest.TestCase)
        for listing in result:
            fingerprint = listing["fingerprint"]
            self.assertIsInstance(fingerprint, str)
            self.assertEqual(len(fingerprint), 64)
            int(fingerprint, 16)

    async def test_contract_idempotent(self) -> None:
        """Scraping the same page twice yields the same fingerprints."""
        first = await self.fetch_from_fixture()
        second = await self.fetch_from_fixture()
        assert isinstance(self, unittest.TestCase)
        self.assertEqual(
            [listing["fingerprint"] for listing in first],
            [listing["fingerprint"] for listing in second],
        )
