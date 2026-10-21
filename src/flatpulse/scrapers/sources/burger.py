"""Burger Immobilier scraper."""

from itertools import count
from typing import Any
from urllib.parse import urljoin

import httpx
from parsel import Selector

from flatpulse.common.utils import parse_rooms, parse_surface, parse_swiss_price
from flatpulse.scrapers.base import HttpScraper


class BurgerScraper(HttpScraper):
    """Scraper for Burger Immobilier listings."""

    base_url = "https://burger-sa.ch/fr/louer"

    def listing_nodes(self, page: Selector) -> list[Selector]:
        """Return the listing nodes from the page."""
        return page.css("div.bien-item")

    def parse_listing(self, node: Selector) -> dict[str, Any]:
        """Parse a single listing node."""
        href = node.css("a::attr(href)").get()
        if href is None:
            raise ValueError("Listing node missing href attribute")
        url = urljoin(self.base_url, href)
        features = " ".join(node.css("div.text-primary::text").getall())
        return {
            "external_url": url,
            "external_id": url,
            "title": node.css("h2::text").get(),
            "price_chf": parse_swiss_price(node.css("div.font-bold::text").get()),
            "nb_rooms": parse_rooms(features),
            "surface_m2": parse_surface(features),
            "images": [
                urljoin(self.base_url, src)
                for src in node.css("img::attr(data-src)").getall()
            ],
        }

    async def fetch_listings(self) -> list[dict[str, Any]]:
        """Walk ?page=1, 2… until a page brings no new card (infinite scroll, no page count).

        Cards without a room count (parkings, commercial units) are dropped.
        """
        listings: dict[str, dict[str, Any]] = {}
        async with httpx.AsyncClient() as client:
            for page_number in count(1):
                response = await client.get(f"{self.base_url}?page={page_number}")
                response.raise_for_status()
                page = Selector(text=response.text)
                seen = len(listings)
                for node in self.listing_nodes(page):
                    listing = self._build_listing(self.parse_listing(node))
                    listings.setdefault(listing["external_url"], listing)
                if len(listings) == seen:
                    break
        return [
            listing for listing in listings.values() if listing["nb_rooms"] is not None
        ]
