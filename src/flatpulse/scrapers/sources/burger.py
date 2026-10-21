"""Burger Immobilier scraper."""

from typing import Any
from urllib.parse import urljoin

from parsel import Selector

from flatpulse.common.utils import parse_rooms, parse_surface, parse_swiss_price
from flatpulse.scrapers.base import HttpScraper


class BurgerScraper(HttpScraper):
    """Scraper for Burger Immobilier listings."""

    base_url = "https://burger-sa.ch/fr/louer?page=N"

    def listing_nodes(self, page: Selector) -> list[Selector]:
        """Return the listing nodes from the page."""
        return page.css("div.bien-item")

    def parse_listing(self, node: Selector) -> dict[str, Any]:
        """Parse a single listing node."""
        href = node.css("a::attr(href)").get()
        if href is None:
            raise ValueError("Listing node missing href attribute")
        return {
            "external_url": urljoin(self.base_url, href),
            "external_id": href.rstrip("/").rsplit("/", 1)[-1],
            "title": node.css("h2::text").get(),  # h2
            "price_chf": parse_swiss_price(node.css("div.font-bold::text").get()),
            "nb_rooms": parse_rooms(node.css("div.font-bold::text").get()),
            "surface_m2": parse_surface(node.css("div.font-bold::text").get()),
            "images": node.css("img::attr(data-src)").getall(),
        }
