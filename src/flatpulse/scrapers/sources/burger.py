"""Burger Immobilier scraper."""

import asyncio
from typing import Any
from urllib.parse import urljoin

import httpx
from parsel import Selector

from flatpulse.common.utils import parse_rooms, parse_surface, parse_swiss_price
from flatpulse.scrapers.base import HttpScraper

# docs/spike-agencies.md: 6 annonces/page, pas de Crawl-delay documenté, pacé à
# 4 req/min (6 pages en ~90s) pour rester discret sur un site sans limite publiée.
_PAGE_COUNT = 6
_PAGE_DELAY_SECONDS = 15.0


class BurgerScraper(HttpScraper):
    """Scraper for Burger Immobilier listings."""

    base_url = "https://burger-sa.ch/fr/louer"

    def listing_nodes(self, page: Selector) -> list[Selector]:
        """Return the listing nodes from the page."""
        return page.css("div.bien-item")

    def parse_listing(self, node: Selector) -> dict[str, Any]:
        """Parse a single listing node.

        Price and room/surface text share the `font-bold` class, so the price
        (plain `div.font-bold`) and the icon-row labels (`div.text-sm.uppercase
        .font-bold.text-primary`) need distinct selectors — see docs/spike-agencies.md.
        """
        href = node.css("a::attr(href)").get()
        if href is None:
            raise ValueError("Listing node missing href attribute")
        external_url = urljoin(self.base_url, href)
        icon_texts = node.css(
            "div.text-sm.uppercase.font-bold.text-primary::text"
        ).getall()
        nb_rooms = next(
            (r for t in icon_texts if (r := parse_rooms(t)) is not None), None
        )
        surface_m2 = next(
            (s for t in icon_texts if (s := parse_surface(t)) is not None), None
        )
        return {
            "external_url": external_url,
            "external_id": external_url,
            "title": node.css("h2::text").get(),
            "price_chf": parse_swiss_price(
                node.css("div.font-bold:not(.text-sm)::text").get()
            ),
            "nb_rooms": nb_rooms,
            "surface_m2": surface_m2,
            "images": [
                urljoin(self.base_url, src)
                for src in node.css("img::attr(data-src)").getall()
            ],
        }

    def _is_apartment(self, listing: dict[str, Any]) -> bool:
        """Keep only apartment listings.

        docs/architecture.md §6.1 / docs/spike-agencies.md: the Burger listing page
        mixes flats with parking spaces and commercial units. Every apartment card
        carries a room count ("Appartement X pièces"); non-apartment cards don't, so
        a missing `nb_rooms` is the signal to filter on.
        """
        return listing["nb_rooms"] is not None

    async def fetch_listings(self) -> list[dict[str, Any]]:
        """Fetch and parse every page of the Burger listing catalogue.

        Overridden (rather than relying on HttpScraper's single-page fetch) because
        Burger paginates: docs/spike-agencies.md documents 6 pages of 6 listings each,
        unlike the sources HttpScraper was designed for.
        """
        listings: list[dict[str, Any]] = []
        async with httpx.AsyncClient() as client:
            for page_number in range(1, _PAGE_COUNT + 1):
                if page_number > 1:
                    await asyncio.sleep(_PAGE_DELAY_SECONDS)
                response = await client.get(f"{self.base_url}?page={page_number}")
                response.raise_for_status()
                page = Selector(text=response.text)
                for node in self.listing_nodes(page):
                    listing = self._build_listing(self.parse_listing(node))
                    if self._is_apartment(listing):
                        listings.append(listing)
        return listings
