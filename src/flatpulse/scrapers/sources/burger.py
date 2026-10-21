"""Scraper for Burger Immobilier: the sitemap lists every fiche, each fiche is a listing."""

import logging
import re
from typing import Any
from urllib.parse import urljoin

import httpx
from parsel import Selector

from flatpulse.common.utils import parse_rooms, parse_surface, parse_swiss_price
from flatpulse.scrapers.base import HttpScraper

_NPA_CITY = re.compile(r"\d{4}\s+(.+)")
# The fiche's own block (rent, address, features), not the similar-listing cards below.
_MAIN_BLOCK = "//div[div/div[normalize-space()='Loyer']]"
_DETAILS = "div.space-y-4.mt-6"

LOGGER = logging.getLogger(__name__)


class BurgerScraper(HttpScraper):
    """Scrape Burger rentals: sitemap.php lists every fiche, each fiche is parsed.

    The /fr/louer listing loads through infinite scroll; the sitemap is the complete,
    reliable list of rental fiches (docs/spike-agencies.md).
    """

    base_url = "https://www.burger-sa.ch/fr/louer"
    sitemap_url = "https://www.burger-sa.ch/sitemap.php"

    async def listing_pages(self, client: httpx.AsyncClient) -> list[str]:
        """Every rental fiche listed in the sitemap."""
        sitemap = Selector(text=await self._get(client, self.sitemap_url), type="xml")
        sitemap.remove_namespaces()
        urls = [
            url
            for url in sitemap.xpath("//url/loc/text()").getall()
            if url.startswith(f"{self.base_url}/")
        ]
        if not urls:
            raise ValueError(
                f"Sitemap Burger sans fiche {self.base_url}/… : format changé ?"
            )
        return urls

    def listing_nodes(self, page: Selector) -> list[Selector]:
        """A fiche page is one listing; without its rent block, the markup changed."""
        if not page.xpath(_MAIN_BLOCK):
            LOGGER.warning(
                "Fiche Burger illisible, bloc Loyer absent : %s",
                page.css("link[rel=canonical]::attr(href), h1::text").get(),
            )
            return []
        return [page]

    def parse_listing(self, node: Selector) -> dict[str, Any]:
        """Extract the listing from a fiche page, ignoring the similar-listing cards."""
        url = node.css("link[rel=canonical]::attr(href)").get()
        site = node.css("base::attr(href)").get() or self.base_url
        sidebar = node.xpath(_MAIN_BLOCK)
        place = [
            line.strip()
            for line in sidebar.css(f"{_DETAILS} div.text-base::text").getall()
        ]
        city = next((m[1] for line in place if (m := _NPA_CITY.fullmatch(line))), None)
        features = self._features(node)
        rent = "./div/div[normalize-space()='Loyer']/following-sibling::div[1]"
        return {
            "external_url": url,
            "external_id": url,
            "title": node.css("h1::text").get(),
            "price_chf": parse_swiss_price(sidebar.xpath(f"string({rent})").get()),
            "nb_rooms": parse_rooms(features) or None,  # "0.0 pièces" means unknown
            "surface_m2": parse_surface(features),
            "address": place[0] if place else None,
            "city": city,
            "description": node.xpath(
                "normalize-space(//div[contains(@class, 'prose')])"
            ).get()
            or None,
            "images": [
                urljoin(site, src)
                for src in node.css("div.swiper-slide img::attr(data-src)").getall()
            ],
        }

    @staticmethod
    def _features(page: Selector) -> str:
        """Type, rooms and surface lines of the fiche, e.g. "Studio 1.0 pièces 36 m2"."""
        texts = page.xpath(_MAIN_BLOCK).css(f"{_DETAILS} div.text-sm::text").getall()
        return " ".join(texts).strip()
