"""Invariants every HTTP scraper must satisfy, inherited by each scraper's test."""

import unittest
from collections.abc import Mapping
from unittest.mock import AsyncMock, patch

from flatpulse.common.models import Listing
from flatpulse.scrapers.base import HttpScraper
from flatpulse.scrapers.rate_limiter import RateLimiter
from tests.helpers import response_from_fixture


class ScraperContractMixin:
    """Contract tests shared by every scraper, and helpers for its named cases.

    Combine with `unittest.IsolatedAsyncioTestCase` and set `scraper_class` and
    `fixture_name`; the scraper then runs against the frozen fixture, never the network,
    with a mocked limiter so the contracts never wait.
    """

    scraper_class: type[HttpScraper]
    fixture_name: str

    def new_scraper(self) -> HttpScraper:
        """A fresh scraper with its own mocked limiter."""
        return self.scraper_class(rate_limiter=AsyncMock(spec=RateLimiter))

    async def fetch_from_fixture(self) -> list[Listing]:
        """Run a fresh scraper against the frozen fixture."""
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = response_from_fixture(self.fixture_name)
            return await self.new_scraper().fetch_listings()

    async def assert_listing(
        self, external_id: str, expected: Mapping[str, object]
    ) -> None:
        """The fixture listing `external_id` has exactly the `expected` field values.

        Only the given fields are compared, so a case pins the fields that are right
        today and leaves the others to the stories that fix them.
        """
        assert isinstance(self, unittest.TestCase)
        listings = await self.fetch_from_fixture()
        listing = next(
            (item for item in listings if item.external_id == external_id), None
        )
        if listing is None:
            self.fail(f"Aucune annonce {external_id!r} dans {self.fixture_name}")
        self.assertEqual(
            {field: getattr(listing, field) for field in expected}, expected
        )

    async def test_contract_fixture_is_not_empty(self) -> None:
        """The fixture yields at least one listing, so the other contracts check something."""
        result = await self.fetch_from_fixture()
        assert isinstance(self, unittest.TestCase)
        self.assertTrue(result, f"{self.fixture_name} ne produit aucune annonce")

    async def test_contract_returns_list(self) -> None:
        """fetch_listings returns a list of dicts."""
        result = await self.fetch_from_fixture()
        assert isinstance(self, unittest.TestCase)
        self.assertIsInstance(result, list)
        for listing in result:
            self.assertIsInstance(listing, Listing)

    async def test_contract_listings_are_immutable(self) -> None:
        """Listings are frozen down to their images, so they can be hashed."""
        result = await self.fetch_from_fixture()
        assert isinstance(self, unittest.TestCase)
        for listing in result:
            self.assertIsInstance(listing.images, tuple)
            hash(listing)

    async def test_contract_has_fingerprint(self) -> None:
        """Each listing carries a 64-character hex SHA-256 fingerprint."""
        result = await self.fetch_from_fixture()
        assert isinstance(self, unittest.TestCase)
        for listing in result:
            fingerprint = listing.fingerprint
            self.assertIsInstance(fingerprint, str)
            self.assertEqual(len(fingerprint), 64)
            int(fingerprint, 16)

    async def test_contract_idempotent(self) -> None:
        """Scraping the same page twice yields the same fingerprints."""
        first = await self.fetch_from_fixture()
        second = await self.fetch_from_fixture()
        assert isinstance(self, unittest.TestCase)
        self.assertEqual(
            [listing.fingerprint for listing in first],
            [listing.fingerprint for listing in second],
        )
