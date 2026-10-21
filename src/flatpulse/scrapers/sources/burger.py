"""Scraper for Burger Immobilier: the sitemap lists every fiche, each fiche is a listing."""

import logging
from typing import Any
from urllib.parse import urljoin

import httpx
from parsel import Selector

from flatpulse.common.utils import parse_rooms, parse_surface, parse_swiss_price
from flatpulse.scrapers.base import HttpScraper

LOGGER = logging.getLogger(__name__)

SITE = "https://www.burger-sa.ch/"


class BurgerScraper(HttpScraper):
    """Scrape Burger rentals: sitemap.php lists every fiche, each fiche is parsed.

    The /fr/louer listing loads through infinite scroll; the sitemap is the complete
    list of rental fiches (docs/spike-agencies.md).
    """

    base_url = SITE + "fr/louer"
    sitemap_url = SITE + "sitemap.php"

    async def listing_pages(self, client: httpx.AsyncClient) -> list[str]:
        """Every rental fiche listed in the sitemap."""
        sitemap = Selector(text=await self._get(client, self.sitemap_url), type="xml")
        sitemap.remove_namespaces()
        urls = [
            url
            for url in sitemap.xpath("//loc/text()").getall()
            if url.startswith(self.base_url + "/")
        ]
        if not urls:
            raise ValueError("Sitemap Burger sans fiche /fr/louer/ : format changé ?")
        return urls

    def listing_nodes(self, page: Selector) -> list[Selector]:
        """The fiche page, unless its details block is missing (markup changed)."""
        if not page.css("div.space-y-4.mt-6"):
            url = page.css("link[rel=canonical]::attr(href)").get()
            LOGGER.warning("Fiche Burger illisible : %s", url)
            return []
        return [page]

    def parse_listing(self, node: Selector) -> dict[str, Any]:
        """Extract the listing from a fiche page."""
        url = node.css("link[rel=canonical]::attr(href)").get()
        details = node.css("div.space-y-4.mt-6")
        address = [line.strip() for line in details.css("div.text-base::text").getall()]
        features = " ".join(details.css("div.text-sm::text").getall())
        rent = node.xpath("//div[text()='Loyer']/following-sibling::div/text()").get()
        return {
            "external_url": url,
            "external_id": url,
            "title": node.css("h1::text").get(),
            "price_chf": parse_swiss_price(rent),
            "nb_rooms": parse_rooms(features) or None,  # "0.0 pièces" means unknown
            "surface_m2": parse_surface(features),
            "address": address[0] if address else None,
            "city": address[1].split(maxsplit=1)[1] if len(address) > 1 else None,
            "description": node.css("div.prose").xpath("normalize-space()").get(),
            "images": [
                urljoin(SITE, src)
                for src in node.css("div.swiper-slide img::attr(data-src)").getall()
            ],
        }
