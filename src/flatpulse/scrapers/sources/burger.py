"""Scraper for Burger Immobilier: the sitemap lists every fiche, each fiche is a listing."""

from typing import Any
from urllib.parse import urljoin

import httpx
from parsel import Selector

from flatpulse.common.utils import parse_rooms, parse_surface, parse_swiss_price
from flatpulse.scrapers.base import HttpScraper


class BurgerScraper(HttpScraper):
    """Scrape every rental fiche listed in Burger's sitemap."""

    base_url = "https://www.burger-sa.ch/sitemap.php"

    def listing_nodes(self, page: Selector) -> list[Selector]:
        """The sitemap entries of the rental fiches."""
        return page.xpath("//*[local-name()='loc'][contains(text(), '/fr/louer/')]")

    def parse_listing(self, node: Selector) -> dict[str, Any]:
        """Download a fiche from its sitemap entry and extract the listing."""
        response = httpx.get(node.xpath("text()").get(""))
        response.raise_for_status()
        fiche = Selector(text=response.text)
        url = fiche.css("link[rel=canonical]::attr(href)").get()
        details = fiche.css("div.space-y-4.mt-6")
        address = [line.strip() for line in details.css("div.text-base::text").getall()]
        features = " ".join(details.css("div.text-sm::text").getall())
        rent = fiche.xpath("//div[text()='Loyer']/following-sibling::div/text()").get()
        return {
            "external_url": url,
            "external_id": url,
            "title": fiche.css("h1::text").get(),
            "price_chf": parse_swiss_price(rent),
            "nb_rooms": parse_rooms(features) or None,  # "0.0 pièces" means unknown
            "surface_m2": parse_surface(features),
            "address": address[0] if address else None,
            "city": address[1].split(maxsplit=1)[1] if len(address) > 1 else None,
            "description": fiche.css("div.prose").xpath("normalize-space()").get(),
            "images": [
                urljoin(self.base_url, src)
                for src in fiche.css("div.swiper-slide img::attr(data-src)").getall()
            ],
        }
