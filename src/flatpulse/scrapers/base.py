"""Base classes defining the contract every listing scraper must follow."""

import asyncio
import logging
from abc import ABC, abstractmethod

import httpx
from parsel import Selector

from flatpulse.common.models import Listing

logger = logging.getLogger(__name__)


class AbstractScraper(ABC):
    """Contract every scraper must implement, regardless of source technology."""

    rate_limit_seconds: float = 0.0

    @abstractmethod
    async def fetch_listings(self) -> list[Listing]:
        """Fetch and return listings as a list of Listing."""
        raise NotImplementedError

    async def run(self) -> list[Listing]:
        """Orchestrate a scrape: wait for the rate limit, then fetch listings."""
        if self.rate_limit_seconds:
            await asyncio.sleep(self.rate_limit_seconds)
        return await self.fetch_listings()


class HttpScraper(AbstractScraper):
    """Base class for HTTP scrapers."""

    base_url: str

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
            try:
                listings.append(self.parse_listing(node))
            except ValueError as exc:
                listing_name = (
                    node.css("a::text").get()
                    or node.attrib.get("data-id")
                    or "unknown listing"
                )
                logger.warning("Skipped invalid listing %r: %s", listing_name, exc)
        return listings
