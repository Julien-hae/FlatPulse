"""Base classes defining the contract every listing scraper must follow."""

import asyncio
import hashlib
import re
from abc import ABC, abstractmethod
from typing import Any

import httpx
from parsel import Selector

REQUIRED_FIELDS = ("external_id", "external_url", "title")
OPTIONAL_FIELDS = (
    "price_chf",
    "nb_rooms",
    "surface_m2",
    "floor",
    "address",
    "city",
    "description",
    "images",
)

_PRICE_PATTERN = re.compile(r"[\d']+(?:\.\d+)?")


class AbstractScraper(ABC):
    """Contract every scraper must implement, regardless of source technology."""

    rate_limit_seconds: float = 0.0

    @abstractmethod
    async def fetch_listings(self) -> list[dict[str, Any]]:
        """Fetch and return listings as a list of plain dicts."""
        raise NotImplementedError

    async def run(self) -> list[dict[str, Any]]:
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
    def parse_listing(self, node: Selector) -> dict[str, Any]:
        """Extract raw fields from a single listing node.

        Must include the required keys (`external_id`, `external_url`,
        `title`); any optional key from `OPTIONAL_FIELDS` may be omitted
        when absent from the page, rather than set to None.
        """
        raise NotImplementedError

    async def _get_html(self) -> str:
        """Fetch the HTML content of the base URL."""
        async with httpx.AsyncClient() as client:
            response = await client.get(self.base_url)
        response.raise_for_status()
        return response.text

    async def fetch_listings(self) -> list[dict[str, Any]]:
        """Download the listing page and parse it into a list of dicts."""
        html = await self._get_html()
        page = Selector(text=html)
        return [
            self._build_listing(self.parse_listing(node))
            for node in self.listing_nodes(page)
        ]

    def _build_listing(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Build a complete listing dict from raw parsed data.

        Ensures all required fields are present and fills in optional fields if available.
        Computes a fingerprint for the listing based on its URL, title, and price.
        """
        listing = {field: raw[field] for field in REQUIRED_FIELDS}
        for field in OPTIONAL_FIELDS:
            listing[field] = raw.get(field)
        listing["fingerprint"] = self._fingerprint(
            listing["external_url"], listing["title"], listing["price_chf"]
        )
        return listing

    @staticmethod
    def _fingerprint(external_url: str, title: str, price_chf: str) -> str:
        """Compute a unique fingerprint for a listing based on its URL, title, and price."""
        fingerprint_source = f"{external_url}|{title}|{price_chf}"
        return hashlib.sha256(fingerprint_source.encode()).hexdigest()

    @staticmethod
    def parse_price_chf(price_str: str | None) -> float | None:
        """Parse a Swiss-formatted CHF price (e.g. "CHF 2'320.-") into a float.

        Returns None when `price_str` is falsy or contains no digits, instead of
        raising, so a missing/unparsable price never crashes a scrape.
        """
        if not price_str:
            return None
        match = _PRICE_PATTERN.search(price_str)
        if not match:
            return None
        return float(match.group().replace("'", ""))
