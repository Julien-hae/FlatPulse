"""Scraper for Comptoir Immobilier, whose rental catalogue is paginated static HTML."""

from typing import Any

import httpx
from parsel import Selector

from flatpulse.common.utils import parse_rooms, parse_surface, parse_swiss_price
from flatpulse.scrapers.base import HttpScraper


class ComptoirScraper(HttpScraper):
    """Scrape rental listings from the Comptoir Immobilier catalogue."""

    base_url = "https://comptoir-immo.ch/location/"

    def listing_nodes(self, page: Selector) -> list[Selector]:
        """Return one node per property card on the page."""
        return list(page.css("article.teaser--property_for_rent"))

    @staticmethod
    def nb_pages(page: Selector) -> int:
        """Return the number of pages announced by the pagination links."""
        numbers = [
            int(text.strip())
            for text in page.css("a.page-number.page-numbers::text").getall()
            if text.strip().isdigit()
        ]
        return max(numbers, default=1)

    async def fetch_listings(self) -> list[dict[str, Any]]:
        """Fetch every catalogue page and parse its property cards."""
        listings: list[dict[str, Any]] = []
        async with httpx.AsyncClient() as client:
            page_number, last_page = 1, 1
            while page_number <= last_page:
                response = await client.get(f"{self.base_url}?page={page_number}")
                response.raise_for_status()
                page = Selector(text=response.text)
                if page_number == 1:
                    last_page = self.nb_pages(page)
                listings.extend(
                    self._build_listing(self.parse_listing(node))
                    for node in self.listing_nodes(page)
                )
                page_number += 1
        return listings

    def parse_listing(self, node: Selector) -> dict[str, Any]:
        """Extract the listing fields from a property card."""
        tags = [
            tag.xpath("normalize-space()").get("")
            for tag in node.css("div.inline-block")
        ]
        rooms = next((tag for tag in tags if "pièce" in tag.lower()), None)
        return {
            "title": node.css("h2").xpath("normalize-space()").get(),
            "external_url": node.css("a:has(h2)::attr(href)").get(),
            "price_chf": parse_swiss_price(node.css("div.heading-4::text").get()),
            "surface_m2": self._get_surface(node),
            "nb_rooms": parse_rooms(rooms),
            "external_id": self._get_id(node),
            "description": self._get_description(node),
        }

    def _get_id(self, node: Selector) -> str:
        """Return the listing slug from the card URL (no reference on the list page)."""
        url = node.css("a:has(h2)::attr(href)").get()
        if not url:
            raise ValueError("ID not found")
        return url.rstrip("/").rsplit("/", 1)[-1]

    def _get_description(self, node: Selector) -> str | None:
        """Return the description text."""
        return node.css("div.rich-text").xpath("normalize-space()").get()

    def _get_surface(self, node: Selector) -> float | None:
        """Return the surface in m2."""
        surface = node.css("div.inline-block").xpath("normalize-space()").get()
        return parse_surface(surface)
