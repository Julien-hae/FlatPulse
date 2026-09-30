"""Contract tests every scraper must satisfy, shared through a mixin."""

import asyncio
import json
import unittest
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar
from unittest.mock import AsyncMock, MagicMock, patch

from flatpulse.scrapers.base import AbstractScraper
from tests.unit.test_scrapers import MinimalScraper

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


if TYPE_CHECKING:
    _MixinBase = unittest.TestCase
else:
    _MixinBase = object


def load_fixture(filename: str) -> str:
    """Return the content of a frozen fixture from `tests/fixtures/`."""
    return (FIXTURES_DIR / filename).read_text(encoding="utf-8")


class ScraperContractMixin(_MixinBase):
    """Invariants shared by every scraper, to be mixed into its `TestCase`.

    The concrete test class must set `self.scraper` and `self.fixture` (the raw
    body the mocked HTTP call returns) in `setUp`.
    """

    scraper: AbstractScraper
    fixture: str

    def fetch(self) -> list[dict[str, Any]]:
        """Run `fetch_listings` against the fixture, without touching the network."""
        response = MagicMock()
        response.text = self.fixture
        # JSON sources read the body through `.json()`, HTML ones through `.text`.
        response.json.side_effect = lambda: json.loads(self.fixture)
        response.raise_for_status.return_value = None
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = response
            return asyncio.run(self.scraper.fetch_listings())

    def test_contract_returns_list(self) -> None:
        """`fetch_listings()` returns a list."""
        self.assertIsInstance(self.fetch(), list)

    def test_contract_required_fields(self) -> None:
        """Every listing has a non-empty id, an http(s) url and a non-empty title."""
        for listing in self.fetch():
            for field in ("external_id", "external_url", "title"):
                self.assertIn(field, listing)
            for field in ("external_id", "title"):
                self.assertIsInstance(listing[field], str)
                self.assertTrue(listing[field].strip(), f"{field} is empty")
            self.assertTrue(listing["external_url"].startswith("http"))

    def test_contract_has_fingerprint(self) -> None:
        """Every listing has a 64-character hexadecimal fingerprint."""
        for listing in self.fetch():
            self.assertIn("fingerprint", listing)
            self.assertRegex(listing["fingerprint"], r"^[0-9a-f]{64}$")

    def test_contract_idempotent(self) -> None:
        """Two fetches of the same content give the same listings, in the same order."""
        first, second = self.fetch(), self.fetch()
        self.assertEqual(len(first), len(second))
        self.assertEqual(
            [listing["fingerprint"] for listing in first],
            [listing["fingerprint"] for listing in second],
        )


class TestMinimalScraperContract(ScraperContractMixin, unittest.TestCase):
    """The contracts hold on the reference scraper built for the base class."""

    def setUp(self) -> None:
        self.scraper = MinimalScraper()
        self.fixture = load_fixture("sample_listing.html")


class BrokenScraper(MinimalScraper):
    """Scraper that breaks exactly one contract, selected by `flaw`."""

    def __init__(self, flaw: str) -> None:
        self.flaw = flaw
        self.calls = 0

    async def fetch_listings(self) -> list[dict[str, Any]]:
        self.calls += 1
        listings = await super().fetch_listings()
        match self.flaw:
            case "not_a_list":
                return tuple(listings)  # type: ignore[return-value]
            case "empty_id":
                listings[0]["external_id"] = ""
            case "relative_url":
                listings[0]["external_url"] = "/louer/1"
            case "empty_title":
                listings[0]["title"] = ""
            case "no_fingerprint":
                del listings[0]["fingerprint"]
            case "short_fingerprint":
                listings[0]["fingerprint"] = "abc123"
            case "non_hex_fingerprint":
                listings[0]["fingerprint"] = "z" * 64
            case "unstable_order":
                if self.calls % 2:
                    listings.reverse()
            case "unstable_length":
                return listings[: len(listings) - self.calls % 2]
        return listings


class TestContractsDetectViolations(unittest.TestCase):
    """A contract that never fails protects nothing: each one must catch a flaw."""

    FLAWS: ClassVar[dict[str, list[str]]] = {
        "test_contract_returns_list": ["not_a_list"],
        "test_contract_required_fields": ["empty_id", "relative_url", "empty_title"],
        "test_contract_has_fingerprint": [
            "no_fingerprint",
            "short_fingerprint",
            "non_hex_fingerprint",
        ],
        "test_contract_idempotent": ["unstable_order", "unstable_length"],
    }

    def test_each_contract_fails_on_its_violation(self) -> None:
        """Check that each contract test fails when the scraper is broken in the right way."""
        for contract, flaws in self.FLAWS.items():
            for flaw in flaws:
                with self.subTest(contract=contract, flaw=flaw):
                    case = TestMinimalScraperContract(contract)
                    case.setUp()
                    case.scraper = BrokenScraper(flaw)
                    with self.assertRaises(AssertionError):
                        getattr(case, contract)()
