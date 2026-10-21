"""Scraper for Burger Immobilier: the sitemap lists every fiche, each fiche is a listing."""

import logging
import re
from typing import Any
from urllib.parse import urljoin

import httpx
from parsel import Selector

from flatpulse.common.utils import parse_rooms, parse_surface, parse_swiss_price
from flatpulse.scrapers.base import HttpScraper

# Type label opening a fiche's feature list; non-dwellings are Bureau, Commerce,
# Dépôt, Arcade, Garage individuel, Place ouverte (docs/spike-agencies.md).
_DWELLING = re.compile(r"(Appartement|Studio|Maison)\b")
_NPA_CITY = re.compile(r"\d{4}\s+(.+)")
# The fiche's own block (rent, address, features), not the similar-listing cards below.
_MAIN_BLOCK = "//div[div/div[normalize-space()='Loyer']]"
_DETAILS = "div.space-y-4.mt-6"

LOGGER = logging.getLogger(__name__)


class BurgerScraper(HttpScraper):
    """Scrape Burger rentals from sitemap.php and the fiche pages.

    The /fr/louer listing loads through infinite scroll, while the sitemap lists every
    fiche with its lastmod: only new or changed fiches are downloaded, at most
    `max_fiches_per_poll` per poll, new fiches first, the others coming at the next
    polls. A fiche that fails to download is logged and retried at the next poll.
    The known fiches live on the instance: the pipeline must reuse it between polls.
    """

    base_url = "https://www.burger-sa.ch/fr/louer"
    sitemap_url = "https://www.burger-sa.ch/sitemap.php"
    # Sitemap + 5 fiches every 90 s = 4 req/min, the rate measured in the spike. Stopgap
    # until the per-source RateLimiter throttles each request (docs/architecture.md §11).
    max_fiches_per_poll = 5

    def __init__(self) -> None:
        """Start with no known fiche."""
        # fiche URL -> (lastmod, listing, or None when the fiche is not a dwelling)
        self._fiches: dict[str, tuple[str, dict[str, Any] | None]] = {}

    def listing_nodes(self, page: Selector) -> list[Selector]:
        """A fiche page is one listing, or none when it is not a dwelling."""
        return [page] if _DWELLING.match(self._features(page)) else []

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

    async def fetch_listings(self) -> list[dict[str, Any]]:
        """Refresh new or changed fiches from the sitemap; return every known dwelling."""
        async with httpx.AsyncClient() as client:
            sitemap = Selector(
                text=await self._get(client, self.sitemap_url), type="xml"
            )
            sitemap.remove_namespaces()
            lastmods = {
                url: entry.xpath("string(lastmod)").get("")
                for entry in sitemap.xpath("//url")
                if (url := entry.xpath("string(loc)").get("")).startswith(
                    f"{self.base_url}/"
                )
            }
            new = [url for url in lastmods if url not in self._fiches]
            changed = [
                url
                for url, lastmod in lastmods.items()
                if url in self._fiches and self._fiches[url][0] != lastmod
            ]
            for url in (new + changed)[: self.max_fiches_per_poll]:
                try:
                    html = await self._get(client, url)
                except httpx.HTTPError as error:
                    LOGGER.warning("Fiche Burger %s non récupérée : %r", url, error)
                    continue
                nodes = self.listing_nodes(Selector(text=html))
                listing = (
                    self._build_listing(self.parse_listing(nodes[0])) if nodes else None
                )
                self._fiches[url] = (lastmods[url], listing)
        self._fiches = {u: f for u, f in self._fiches.items() if u in lastmods}
        return [listing for _, listing in self._fiches.values() if listing]

    @staticmethod
    def _features(page: Selector) -> str:
        """Type, rooms and surface lines of the fiche's main block, e.g. "Studio 1.0 pièces 36 m2"."""
        texts = page.xpath(_MAIN_BLOCK).css(f"{_DETAILS} div.text-sm::text").getall()
        return " ".join(texts).strip()

    @staticmethod
    async def _get(client: httpx.AsyncClient, url: str) -> str:
        """GET a page and return its body, raising on HTTP errors."""
        response = await client.get(url)
        response.raise_for_status()
        return str(response.text)
