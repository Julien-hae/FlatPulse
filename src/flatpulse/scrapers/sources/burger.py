"""Scraper for Burger Immobilier: the sitemap lists every fiche, each fiche is a listing."""

import logging
from typing import Any
from urllib.parse import urljoin

import httpx
from parsel import Selector

from flatpulse.common.utils import parse_rooms, parse_surface, parse_swiss_price
from flatpulse.scrapers.base import HttpScraper


class BurgerScraper(HttpScraper):
    """Scrape every rental fiche listed in Burger's sitemap."""

    base_url = "https://www.burger-sa.ch/sitemap.php"

    async def fetch_listings(self) -> list[dict[str, Any]]:
        """Download the sitemap, then each rental fiche it lists; skip failing fiches."""
        listings: list[dict[str, Any]] = []
        async with httpx.AsyncClient() as client:
            sitemap = await client.get(self.base_url)
            sitemap.raise_for_status()
            for node in self.listing_nodes(Selector(text=sitemap.text)):
                url = node.xpath("text()").get("")
                try:
                    fiche = await client.get(url)
                    fiche.raise_for_status()
                except httpx.HTTPError as error:
                    logging.getLogger(__name__).warning(
                        "Fiche %s ignorée : %r", url, error
                    )
                    continue
                listing = self.parse_listing(Selector(text=fiche.text), url)
                listings.append(self._build_listing(listing))
        return listings

    def listing_nodes(self, page: Selector) -> list[Selector]:
        """The sitemap entries of the rental fiches."""
        return page.xpath("//*[local-name()='loc'][contains(text(), '/fr/louer/')]")

    def parse_listing(self, node: Selector, url: str | None = None) -> dict[str, Any]:
        """Extract the listing from a fiche page, known by `url` or by its canonical link."""
        url = url or node.css("link[rel=canonical]::attr(href)").get()
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
            "city": self.city(address),
            "description": node.css("div.prose").xpath("normalize-space()").get()
            or None,
            "images": [
                urljoin(self.base_url, src)
                for src in node.css("div.swiper-slide img::attr(data-src)").getall()
            ],
        }

    @staticmethod
    def city(address: list[str]) -> str | None:
        """Town of the "NPA town" address line, e.g. "1204 Genève"; None without one."""
        for line in address[1:]:
            npa, _, town = line.partition(" ")
            if npa.isdigit() and town:
                return town
        return None
