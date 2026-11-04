"""Scraper for Comptoir Immobilier: the catalogue lists the fiches, each fiche is a listing."""

import asyncio
import logging
from functools import partial

import httpx
from parsel import Selector, SelectorList

from flatpulse.common.models import Listing
from flatpulse.common.utils import (
    canton_code,
    is_monthly_rent,
    parse_floor,
    parse_monthly_rent,
    parse_property_type,
    parse_rooms,
    parse_surface,
    parse_swiss_price,
)
from flatpulse.scrapers.base import HttpScraper

logger = logging.getLogger(__name__)


class ComptoirScraper(HttpScraper):
    """Scrape every rental fiche of the Comptoir Immobilier catalogue."""

    base_url = "https://comptoir-immo.ch/location/"
    rate_limit_seconds = 10  # Crawl-delay of robots.txt, waited before every request

    async def fetch_listings(self) -> list[Listing]:
        """Walk the catalogue, then parse each fiche; skip failing or invalid ones."""
        listings: list[Listing] = []
        async with httpx.AsyncClient() as client:
            for url in await self._fiche_urls(client):
                try:
                    fiche = await self._get(client, url)
                except httpx.HTTPError as error:
                    logger.warning("Fiche %s ignorée : %r", url, error)
                    continue
                listing = self._parse_or_skip(partial(self.parse_listing, fiche))
                if listing is not None:
                    listings.append(listing)
        return listings

    def listing_nodes(self, page: Selector) -> list[Selector]:
        """Return one node per property card on a catalogue page."""
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

    def parse_listing(self, node: Selector) -> Listing:
        """Extract the listing from a fiche, mostly from its « Détails » table."""
        url = node.css("link[rel=canonical]::attr(href)").get("")
        city, _, canton = (self._text(node.css("h1 + h2")) or "").partition(", ")
        rent = self._detail(node, "Loyer")
        # Charges carry no unit: they belong only to a monthly rent.
        monthly = rent is not None and is_monthly_rent(rent)
        charges = self._detail(node, "Charges") if monthly else None
        surface_m2 = parse_surface(self._detail(node, "Surface"))
        return Listing(
            external_url=url,
            external_id=url.rstrip("/").rsplit("/", 1)[-1],
            title=self._text(node.css("h1")) or "",
            property_type=parse_property_type(self._detail(node, "Type de bien")),
            price_chf=parse_monthly_rent(
                self._text(node.css("h1 ~ .heading-3")), surface_m2
            ),
            charges_chf=parse_swiss_price(charges) or None,
            nb_rooms=parse_rooms(self._detail(node, "Pièces")),
            surface_m2=surface_m2,
            floor=parse_floor(self._detail(node, "Etage")),
            address=(self._detail(node, "Adresse") or "").partition(", ")[0] or None,
            city=city or None,
            canton=canton_code(canton),
            description=self._text(node.css("div.rich-text")),
            images=tuple(node.css("[data-gallery] img::attr(src)").getall()),
        )

    def _detail(self, node: Selector, label: str) -> str | None:
        """Value after the « Détails » label starting with `label`, None without one.

        « Surface » reads « Surface habitable » as well as « Surface utile ».
        """
        return self._text(
            node.xpath(
                "//th[starts-with(normalize-space(), $label)]/following-sibling::td[1]",
                label=label,
            )
        )

    @staticmethod
    def _text(nodes: SelectorList[Selector]) -> str | None:
        """Whitespace-normalised text of the first node, None when absent or empty."""
        return nodes.xpath("normalize-space()").get() or None

    async def _fiche_urls(self, client: httpx.AsyncClient) -> list[str]:
        """URLs of the fiches carded on every page of the catalogue."""
        first = await self._get(client, f"{self.base_url}?page=1")
        pages = [first] + [
            await self._get(client, f"{self.base_url}?page={number}")
            for number in range(2, self.nb_pages(first) + 1)
        ]
        return [
            url
            for page in pages
            for node in self.listing_nodes(page)
            if (url := node.css("a:has(h2)::attr(href)").get())
        ]

    async def _get(self, client: httpx.AsyncClient, url: str) -> Selector:
        """GET `url` once the crawl-delay has passed, and parse it."""
        await asyncio.sleep(self.rate_limit_seconds)
        response = await client.get(url)
        response.raise_for_status()
        return Selector(text=response.text)
