"""Unit tests for the scrapers base class."""

import hashlib
import unittest
from collections.abc import Callable
from dataclasses import replace
from unittest.mock import AsyncMock, Mock, call, patch

import httpx
from parsel import Selector

from flatpulse.common.models import Listing
from flatpulse.common.utils import parse_monthly_rent
from flatpulse.scrapers.base import (
    AbstractScraper,
    CatalogueScraper,
    FicheScraper,
    HttpScraper,
)
from flatpulse.scrapers.rate_limiter import RateLimiter
from tests.contract.test_scraper_contract import ScraperContractMixin
from tests.helpers import CANTON_LOOKUP, response_from_fixture


class MinimalScraper(CatalogueScraper):
    """Smallest possible CatalogueScraper, used only to exercise the base classes."""

    base_url = "https://example.com/louer"
    slug = "minimal"

    def listing_nodes(self, page: Selector) -> list[Selector]:
        return page.css("div.listing")

    def parse_listing(self, node: Selector) -> Listing:
        return Listing(
            external_id=node.attrib.get("data-id", ""),
            external_url=node.css("a.title::attr(href)").get(""),
            title=node.css("a.title::text").get(""),
            price_chf=parse_monthly_rent(node.css("span.price::text").get(), None),
        )


class AlternatingInvalidScraper(MinimalScraper):
    """Scraper test double whose middle listing breaks a Listing invariant."""

    def parse_listing(self, node: Selector) -> Listing:
        """Listing 102 gets a rent of 0, which Listing rejects."""
        listing = super().parse_listing(node)
        if listing.external_id == "102":
            return replace(listing, price_chf=0)  # raises ValueError
        return listing


class CrashingParserScraper(MinimalScraper):
    """Scraper test double whose parser crashes on the middle listing."""

    def parse_listing(self, node: Selector) -> Listing:
        """Listing 102 hits a bug of the parser itself, not an invalid field."""
        if node.attrib.get("data-id") == "102":
            raise AttributeError("'NoneType' object has no attribute 'strip'")
        return super().parse_listing(node)


class PostalCodeScraper(MinimalScraper):
    """Scraper test double publishing a postal code, and a canton for listing 102."""

    def parse_listing(self, node: Selector) -> Listing:
        listing = replace(super().parse_listing(node), postal_code="1206")
        if listing.external_id == "102":
            return replace(listing, canton="VD")
        return listing


class MinimalFicheScraper(FicheScraper):
    """Smallest possible FicheScraper: an index of two fiches, each a listing page."""

    base_url = "https://example.com/index"
    slug = "minimal-fiches"
    FICHES = ("https://example.com/fiche/1", "https://example.com/fiche/2")

    async def fiche_urls(self, client: httpx.AsyncClient) -> list[str]:
        await self._get(client, self.base_url)
        return list(self.FICHES)

    def parse_fiche(self, node: Selector, url: str) -> Listing:
        return Listing(
            external_id=url, external_url=url, title=node.css("h1::text").get("")
        )


def fiche_response(title: str = "Appartement à Carouge") -> Mock:
    """A fake httpx response serving a one-title fiche page."""
    return Mock(text=f"<html><h1>{title}</h1></html>")


class TestMinimalScraperContract(
    ScraperContractMixin, unittest.IsolatedAsyncioTestCase
):
    """MinimalScraper honours the shared scraper contract."""

    scraper_class = MinimalScraper
    fixture_name = "same_listing.html"


class TestHttpScraper(unittest.IsolatedAsyncioTestCase):
    """Unit tests for the HttpScraper class."""

    def setUp(self) -> None:
        """A fresh scraper per test, with a mocked limiter so nothing waits."""
        self.scraper = MinimalScraper(
            rate_limiter=AsyncMock(spec=RateLimiter), canton_lookup=CANTON_LOOKUP
        )

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
        scraper = AlternatingInvalidScraper(
            rate_limiter=AsyncMock(spec=RateLimiter), canton_lookup=CANTON_LOOKUP
        )

        with self.assertLogs("flatpulse.scrapers.base", level="WARNING") as captured:
            result = await scraper.fetch_listings()

        self.assertEqual([listing.external_id for listing in result], ["101", "103"])
        [warning] = captured.output
        self.assertIn("price_chf", warning)
        self.assertIn("https://example.com/annonces/102", warning)

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    async def test_crashing_parser_loses_one_listing_not_the_poll(
        self, mock_get: AsyncMock
    ) -> None:
        """A parser bug on one listing is logged with its traceback; the others come out."""
        mock_get.return_value = response_from_fixture("sample_listing.html")
        scraper = CrashingParserScraper(
            rate_limiter=AsyncMock(spec=RateLimiter), canton_lookup=CANTON_LOOKUP
        )

        with self.assertLogs("flatpulse.scrapers.base", level="ERROR") as captured:
            result = await scraper.fetch_listings()

        self.assertEqual([listing.external_id for listing in result], ["101", "103"])
        [error] = captured.output
        self.assertIn("Skipped invalid listing", error)
        self.assertIn("AttributeError", error)
        self.assertIn("Traceback", error)

    async def test_run_does_not_sleep(self) -> None:
        """run delegates to fetch_listings without a separate delay."""
        scraper = MinimalScraper(
            rate_limiter=AsyncMock(spec=RateLimiter), canton_lookup=CANTON_LOOKUP
        )
        with (
            patch.object(
                scraper, "fetch_listings", new_callable=AsyncMock, return_value=[]
            ) as fetch_listings,
            patch("asyncio.sleep", new_callable=AsyncMock) as sleep,
        ):
            result = await scraper.run()

        sleep.assert_not_awaited()
        fetch_listings.assert_awaited_once_with()
        self.assertEqual(result, [])

    def test_scraper_requires_a_rate_limiter(self) -> None:
        """No scraper without a rate: the limiter is a mandatory argument."""
        with self.assertRaises(TypeError):
            MinimalScraper()  # type: ignore[call-arg]

    async def test_single_page_acquires_before_its_request(self) -> None:
        """The single-page path (Naef) acquires a token before its only GET."""
        limiter = AsyncMock(spec=RateLimiter)
        manager = Mock()
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = response_from_fixture("sample_listing.html")
            manager.attach_mock(limiter.acquire, "acquire")
            manager.attach_mock(mock_get, "get")
            await MinimalScraper(
                rate_limiter=limiter, canton_lookup=CANTON_LOOKUP
            ).fetch_listings()

        requests = [c for c in manager.mock_calls if c[0] in ("acquire", "get")]
        self.assertEqual(
            requests, [call.acquire("minimal"), call.get(MinimalScraper.base_url)]
        )


class TestFicheScraper(unittest.IsolatedAsyncioTestCase):
    """What FicheScraper does once, for every source read fiche by fiche."""

    def setUp(self) -> None:
        self.limiter = AsyncMock(spec=RateLimiter)
        self.scraper = MinimalFicheScraper(
            rate_limiter=self.limiter, canton_lookup=CANTON_LOOKUP
        )

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    async def test_each_fiche_of_the_index_is_a_listing(
        self, mock_get: AsyncMock
    ) -> None:
        """The index, then one paced request per fiche, each parsed with its URL."""
        mock_get.return_value = fiche_response()

        listings = await self.scraper.fetch_listings()

        self.assertEqual(
            [listing.external_url for listing in listings],
            list(MinimalFicheScraper.FICHES),
        )
        self.assertEqual(
            [request.args[0] for request in mock_get.await_args_list],
            [MinimalFicheScraper.base_url, *MinimalFicheScraper.FICHES],
        )
        self.assertEqual(self.limiter.acquire.await_count, 3)

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    async def test_failing_fiche_is_skipped_and_logged(
        self, mock_get: AsyncMock
    ) -> None:
        """One dropped connection loses one fiche, not the poll."""
        first, second = MinimalFicheScraper.FICHES

        def get(url: str) -> Mock:
            if url == first:
                raise httpx.RemoteProtocolError("Server disconnected")
            return fiche_response()

        mock_get.side_effect = get

        with self.assertLogs("flatpulse.scrapers.base", "WARNING") as captured:
            listings = await self.scraper.fetch_listings()

        self.assertEqual([listing.external_url for listing in listings], [second])
        [warning] = captured.output
        self.assertIn(first, warning)

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    async def test_invalid_fiche_is_skipped_and_logged(
        self, mock_get: AsyncMock
    ) -> None:
        """A fiche Listing refuses (no title) is skipped; the next one comes out."""
        first, second = MinimalFicheScraper.FICHES
        mock_get.side_effect = lambda url: fiche_response(
            "" if url == first else "Appartement à Carouge"
        )

        with self.assertLogs("flatpulse.scrapers.base", "WARNING") as captured:
            listings = await self.scraper.fetch_listings()

        self.assertEqual([listing.external_url for listing in listings], [second])
        [warning] = captured.output
        self.assertIn("title", warning)

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    async def test_failing_index_is_raised(self, mock_get: AsyncMock) -> None:
        """Without its index the source is down: the pipeline must hear of it."""
        mock_get.side_effect = httpx.ConnectError("Network is unreachable")

        with self.assertRaises(httpx.ConnectError):
            await self.scraper.fetch_listings()


class TestScraperContract(unittest.TestCase):
    """Tests for the abstract contract and Listing building."""

    def test_abstract_classes_cannot_be_instantiated(self) -> None:
        """The base classes are abstract: only the scraper of a source can be built."""
        with self.assertRaises(TypeError):
            AbstractScraper()  # type: ignore[abstract]
        bases: tuple[type[HttpScraper], ...] = (
            HttpScraper,
            CatalogueScraper,
            FicheScraper,
        )
        for base in bases:
            with self.subTest(base=base.__name__), self.assertRaises(TypeError):
                base(
                    rate_limiter=AsyncMock(spec=RateLimiter),
                    canton_lookup=CANTON_LOOKUP,
                )

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


class TestCantonFromPostalCode(unittest.IsolatedAsyncioTestCase):
    """Every HttpScraper completes a canton the source leaves out (#133)."""

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    async def test_missing_canton_is_read_from_postal_code(
        self, mock_get: AsyncMock
    ) -> None:
        """1206 is GE; a canton written by the source is kept as is."""
        mock_get.return_value = response_from_fixture("sample_listing.html")
        scraper = PostalCodeScraper(
            rate_limiter=AsyncMock(spec=RateLimiter), canton_lookup=CANTON_LOOKUP
        )

        listings = await scraper.fetch_listings()

        cantons = {listing.external_id: listing.canton for listing in listings}
        self.assertEqual(cantons.pop("102"), "VD")
        self.assertTrue(cantons)
        self.assertEqual(set(cantons.values()), {"GE"})
