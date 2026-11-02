"""Unit tests for the scrapers base class."""

import hashlib
import unittest
from collections.abc import Callable
from dataclasses import replace
from unittest.mock import AsyncMock, patch

from parsel import Selector

from flatpulse.common.models import Listing
from flatpulse.common.utils import parse_swiss_price
from flatpulse.scrapers.base import (
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

    def parse_listing(self, node: Selector) -> Listing:
        return Listing(
            external_id=node.attrib.get("data-id", ""),
            external_url=node.css("a.title::attr(href)").get(""),
            title=node.css("a.title::text").get(""),
            price_chf=parse_swiss_price(node.css("span.price::text").get()),
        )


class AlternatingInvalidScraper(MinimalScraper):
    """Scraper test double whose middle listing breaks a Listing invariant."""

    def parse_listing(self, node: Selector) -> Listing:
        """Listing 102 gets a rent of 0, which Listing rejects."""
        listing = super().parse_listing(node)
        if listing.external_id == "102":
            return replace(listing, price_chf=0)  # raises ValueError
        return listing


class TestMinimalScraperContract(
    ScraperContractMixin, unittest.IsolatedAsyncioTestCase
):
    """MinimalScraper honours the shared scraper contract."""

    scraper_class = MinimalScraper
    fixture_name = "same_listing.html"


class TestHttpScraper(unittest.IsolatedAsyncioTestCase):
    """Unit tests for the HttpScraper class."""

    scraper = MinimalScraper()

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    async def test_fetch_returns_listings_with_required_fields(
        self, mock_get: AsyncMock
    ) -> None:
        """Test that fetch_listings returns Listing objects with their required fields."""
        mock_get.return_value = response_from_fixture("sample_listing.html")

        result = await self.scraper.fetch_listings()

        mock_get.assert_awaited_once()
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 3)
        for listing in result:
            self.assertIsInstance(listing, Listing)
            self.assertIsNotNone(listing.external_id)
            self.assertTrue(str(listing.external_url).startswith("http"))
            self.assertIsNotNone(listing.title)

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    async def test_missing_price_returns_none(self, mock_get: AsyncMock) -> None:
        """Test that listings with missing or non-numeric prices return None for price_chf and do not crashes."""
        mock_get.return_value = response_from_fixture("listing_no_price.html")

        result = await self.scraper.fetch_listings()

        for listing in result:
            self.assertIsNone(listing.price_chf)

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    async def test_fingerprint_deterministic(self, mock_get: AsyncMock) -> None:
        """Test that the fingerprint method returns the same value for the same input."""
        mock_get.return_value = response_from_fixture("same_listing.html")

        result = await self.scraper.fetch_listings()
        self.assertEqual(result[0].fingerprint, result[1].fingerprint)

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    async def test_fingerprint_changes_on_price_change(
        self, mock_get: AsyncMock
    ) -> None:
        """Test that the fingerprint method returns different values when the price changes."""
        mock_get.return_value = response_from_fixture("different_price.html")

        result = await self.scraper.fetch_listings()
        self.assertNotEqual(result[0].fingerprint, result[1].fingerprint)

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    async def test_invalid_listing_is_skipped_and_logged(
        self, mock_get: AsyncMock
    ) -> None:
        """The pipeline never falls because of one link (CLAUDE.md): skip and log."""
        mock_get.return_value = response_from_fixture("sample_listing.html")
        scraper = AlternatingInvalidScraper()

        with self.assertLogs("flatpulse.scrapers.base", level="WARNING") as captured:
            result = await scraper.fetch_listings()

        self.assertEqual([listing.external_id for listing in result], ["101", "103"])
        [warning] = captured.output
        self.assertIn("price_chf", warning)
        self.assertIn("https://example.com/annonces/102", warning)


class TestScraperContract(unittest.TestCase):
    """Tests for the abstract contract and Listing building."""

    def test_abstract_classes_cannot_be_instantiated(self) -> None:
        """AbstractScraper and HttpScraper are abstract and must not be instantiable."""
        with self.assertRaises(TypeError):
            AbstractScraper()  # type: ignore[abstract]
        with self.assertRaises(TypeError):
            HttpScraper()  # type: ignore[abstract]

    def test_listing_rejects_empty_required_field(self) -> None:
        """A listing without identity breaks the dedup."""
        with self.assertRaises(ValueError):
            Listing(external_id="", external_url="http://example.com", title="Test")

    def test_listing_rejects_zero_price(self) -> None:
        """A 0 passes the price hard filters and triggers absurd alerts (CLAUDE.md)."""
        with self.assertRaises(ValueError):
            Listing(
                external_id="1",
                external_url="http://example.com",
                title="Test",
                price_chf=0,
            )

    def test_listing_keeps_rent_and_charges(self) -> None:
        """price_chf is the monthly rent charges included; charges_chf is its share."""
        listing = Listing(
            external_id="1",
            external_url="https://www.naef.ch/x/",
            title="Studio",
            price_chf=185000,
            charges_chf=20000,
        )

        self.assertEqual((listing.price_chf, listing.charges_chf), (185000, 20000))

    def test_fingerprint_is_unchanged(self) -> None:
        """Same formula as before #114, or the whole stock would look modified."""
        listing = Listing(
            external_id="1",
            external_url="https://www.burger-sa.ch/fr/louer/a",
            title="Studio",
            price_chf=137000,
        )
        source = "https://www.burger-sa.ch/fr/louer/a|Studio|137000"

        self.assertEqual(
            listing.fingerprint, hashlib.sha256(source.encode()).hexdigest()
        )

    def test_external_url_is_kept_as_scraped(self) -> None:
        """No normalisation: the fingerprint hashes the URL the agency published."""
        url = "https://www.Naef.ch:443/location/Genève/x/"

        listing = Listing(external_id="1", external_url=url, title="Studio")

        self.assertEqual(str(listing.external_url), url)

    def test_listing_rejects_non_http_url(self) -> None:
        """A relative, ftp: or mailto: link cannot be sent as the listing's link."""
        for url in ("/fr/louer/a", "ftp://www.naef.ch/a", "mailto:info@naef.ch"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                Listing(external_id="1", external_url=url, title="Studio")

    def test_listing_errors_name_the_field_and_the_url(self) -> None:
        """The skip warning must say which field of which listing is wrong."""
        url = "https://www.naef.ch/location/appartement/1205/x/"
        cases: dict[str, Callable[[], Listing]] = {
            "external_id": lambda: Listing(
                external_id="", external_url=url, title="Studio"
            ),
            "title": lambda: Listing(external_id="1", external_url=url, title=""),
            "price_chf": lambda: Listing(
                external_id="1", external_url=url, title="Studio", price_chf=0
            ),
            "nb_rooms": lambda: Listing(
                external_id="1", external_url=url, title="Studio", nb_rooms=0.0
            ),
            "canton": lambda: Listing(
                external_id="1", external_url=url, title="Studio", canton="Genève"
            ),
        }
        for field, build in cases.items():
            with self.subTest(field=field), self.assertRaises(ValueError) as error:
                build()
            self.assertIn(field, str(error.exception))
            self.assertIn(url, str(error.exception))

    def test_listing_rejects_zero_rooms(self) -> None:
        """« 0 pièce » means unknown at Naef and Burger: it must arrive as None."""
        with self.assertRaises(ValueError):
            Listing(
                external_id="1",
                external_url="http://example.com",
                title="Test",
                nb_rooms=0,
            )

    def test_listing_rejects_zero_or_negative_quantities(self) -> None:
        """Absent is None, never 0: charges, rooms and surface included."""
        url = "https://www.naef.ch/x/"
        cases: dict[str, Callable[[], Listing]] = {
            "price_chf=-100": lambda: Listing(
                external_id="1", external_url=url, title="Studio", price_chf=-100
            ),
            "charges_chf=0": lambda: Listing(
                external_id="1", external_url=url, title="Studio", charges_chf=0
            ),
            "nb_rooms=-1.0": lambda: Listing(
                external_id="1", external_url=url, title="Studio", nb_rooms=-1.0
            ),
            "surface_m2=0.0": lambda: Listing(
                external_id="1", external_url=url, title="Studio", surface_m2=0.0
            ),
            "surface_m2=-5.0": lambda: Listing(
                external_id="1", external_url=url, title="Studio", surface_m2=-5.0
            ),
        }
        for case, build in cases.items():
            with self.subTest(case=case), self.assertRaises(ValueError):
                build()

    def test_listing_rejects_empty_optional_text(self) -> None:
        """An absent text is None, not an empty string."""
        with self.assertRaises(ValueError):
            Listing(
                external_id="1",
                external_url="http://example.com",
                title="Test",
                description="",
            )

    def test_listing_rejects_canton_name(self) -> None:
        """canton is the two-letter code: "GE" passes, a canton name does not."""
        with self.assertRaises(ValueError):
            Listing(
                external_id="1",
                external_url="http://example.com",
                title="Test",
                canton="Geneva",
            )
        listing = Listing(
            external_id="1",
            external_url="http://example.com",
            title="Test",
            canton="GE",
        )
        self.assertEqual(listing.canton, "GE")
