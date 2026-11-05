"""Base classes defining the contract every listing scraper must follow."""

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from functools import partial

import httpx
from parsel import Selector

from flatpulse.common.models import Listing
from flatpulse.config import RPM_BY_SLUG
from flatpulse.scrapers.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


class AbstractScraper(ABC):
    """Contract every scraper must implement, regardless of source technology."""

    @abstractmethod
    async def fetch_listings(self) -> list[Listing]:
        """Fetch and return listings as a list of Listing."""
        raise NotImplementedError

    async def run(self) -> list[Listing]:
        """Orchestrate a scrape: wait for the rate limit, then fetch listings."""
        return await self.fetch_listings()


class HttpScraper(AbstractScraper):
    """Base class for HTTP scrapers."""

    def __init__(self, rate_limiter: RateLimiter | None = None):
        """Initialize with a rate limiter."""
        self.rate_limiter = (
            rate_limiter if rate_limiter else RateLimiter(rpm_by_slug=RPM_BY_SLUG)
        )

    base_url: str
    slug: str

    @abstractmethod
    def listing_nodes(self, page: Selector) -> list[Selector]:
        """Return one Selector per listing found on the parsed page."""
        raise NotImplementedError

    @abstractmethod
    def parse_listing(self, node: Selector) -> Listing:
        """Parse a listing node into a Listing."""
        raise NotImplementedError

    async def _get_html(self) -> str:
        """Fetch the HTML content of the base URL."""
        async with httpx.AsyncClient() as client:
            response = await client.get(self.base_url)
        response.raise_for_status()
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

    @staticmethod
    def _parse_or_skip(parse: Callable[[], Listing]) -> Listing | None:
        """Run `parse`; an invalid listing is logged and skipped, the poll goes on.

        The ValueError names the faulty field and the listing's URL, so the node
        itself (HTML or JSON) is not read again here.
        """
        try:
            return parse()
        except ValueError as error:
            logger.warning("Skipped invalid listing: %s", error)
            return None
