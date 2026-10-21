"""Scraper for Comptoir Immobilier, which exposes its whole catalogue as one JSON payload."""

from typing import Any

from parsel import Selector

from flatpulse.common.utils import parse_rooms, parse_surface, parse_swiss_price
from flatpulse.scrapers.base import HttpScraper


class ComptoirScraper(HttpScraper):
    """Scrape rental listings from the Comptoir Immobilier catalogue."""

    base_url = "https://www.comptoir-immo.ch/location/{appartement,maison}"

    def listing_nodes(self, page: Selector) -> list[Selector]:
        """Return node per property in the payload."""
        return page.css("article.teaser--property_for_rent ")

    def parse_listing(self, node: Selector) -> dict[str, Any]:
        """Extract the listing fields from a property node."""
        title = node.css("h2 div::text").get()
        url = node.css("a:has(h2)::attr(href)").get()
        price = parse_swiss_price(node.css("div.heading-4::text").get())
        tags = node.css("div.inline-block::text").getall()
        tmp_rooms = next((t for t in tags if "pièce" in t.lower()), None)
        tmp_surface = next((t for t in tags if "m²" in t.lower()), None)
        id = node.attrib["data-id"]
        return {
            "title": title,
            "external_url": url,
            "price": price,
            "surface_m2": parse_surface(tmp_surface),
            "nb_rooms": parse_rooms(tmp_rooms),
            "external_id": id,
        }
