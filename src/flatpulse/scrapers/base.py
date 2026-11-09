"""Base classes defining the contract every listing scraper must follow."""

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from functools import partial

import httpx
from parsel import Selector

from flatpulse.common.models import Listing
from flatpulse.common.postal_codes import CantonLookup, fill_missing_canton
from flatpulse.scrapers.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

# Logged for each listing skipped as invalid; the live audit (#119) counts them by it.
SKIPPED_INVALID_LISTING = "Skipped invalid listing: %s"


class AbstractScraper(ABC):
    """Contract every scraper must implement, regardless of source technology."""

    @abstractmethod
    async def fetch_listings(self) -> list[Listing]:
        """Fetch and return listings as a list of Listing."""
        raise NotImplementedError

    async def run(self) -> list[Listing]:
        """Orchestrate a scrape; the pace is set request by request by the limiter."""
        return await self.fetch_listings()


class HttpScraper(AbstractScraper):
    """Base class for HTTP scrapers."""

    base_url: str
    slug: str

    def __init__(self, rate_limiter: RateLimiter, canton_lookup: CantonLookup) -> None:
        """Keep the request limiter of this source and the postal code table.

        The limiter paces every request of `slug`; the table completes a canton the
        source leaves out. Neither has a default: the pipeline builds both.
        """
        self.rate_limiter = rate_limiter
        self.canton_lookup = canton_lookup

    @abstractmethod
    def listing_nodes(self, page: Selector) -> list[Selector]:
        """Return one Selector per listing found on the parsed page."""
        raise NotImplementedError

    @abstractmethod
    def parse_listing(self, node: Selector) -> Listing:
        """Parse a listing node into a Listing."""
        raise NotImplementedError

    async def _get(self, client: httpx.AsyncClient, url: str) -> httpx.Response:
        """GET `url` once the limiter grants this source a token; raise on HTTP error.

        Every request of a scraper goes through here, so none escapes the limiter.
        """
        await self.rate_limiter.acquire(self.slug)
        response = await client.get(url)
        response.raise_for_status()
        return response

    async def _get_html(self) -> str:
        """Fetch the HTML content of the base URL."""
        async with httpx.AsyncClient() as client:
            response = await self._get(client, self.base_url)
        return response.text

    async def fetch_listings(self) -> list[Listing]:
        """Download the listing page and parse it into a list of Listing."""
        html = await self._get_html()
        page = Selector(text=html)
        listings: list[Listing] = []
        for node in self.listing_nodes(page):
            listing = self._parse_or_skip(partial(self.parse_listing, node))
            if listing is not None:
                listings.append(listing)
        return listings

    def _parse_or_skip(self, parse: Callable[[], Listing]) -> Listing | None:
        """Run `parse`; an invalid listing is logged and skipped, the poll goes on.

        A canton the source does not write is completed from the postal code and
        city, here, so every scraper gets it without writing a line. The ValueError
        names the faulty field and the listing's URL, so the node itself (HTML or
        JSON) is not read again here.
        """
        try:
            return fill_missing_canton(parse(), self.canton_lookup)
        except ValueError as error:
            logger.warning(SKIPPED_INVALID_LISTING, error)
            return None
