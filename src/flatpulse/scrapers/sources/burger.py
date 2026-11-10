"""Scraper for Burger Immobilier: the sitemap lists every fiche, each fiche is a listing."""

import logging
import re
from functools import partial
from typing import NamedTuple
from urllib.parse import urljoin

import httpx
from parsel import Selector

from flatpulse.common.models import Listing, PropertyType
from flatpulse.common.utils import (
    parse_charges,
    parse_floor,
    parse_monthly_rent,
    parse_property_type,
    parse_rooms,
    parse_surface,
)
from flatpulse.scrapers.base import HttpScraper

logger = logging.getLogger(__name__)

# The feature rows under the address: « Appartement 3.0 pièces », then « 59 m2 »,
# « ENV. 60 M2 » or « de 85 M2 à 100 M2 » (lower bound kept).
_TYPE_ROW = re.compile(r"(?P<label>\D+?)(?: (?P<rooms>\d+(?:\.\d+)?) pièces)?")
_SURFACE_ROW = re.compile(
    r"(?:env\. ?|de )?(?P<m2>\d+(?:\.\d+)?) m2(?: à \d+(?:\.\d+)? m2)?",
    re.IGNORECASE,
)


class _Locality(NamedTuple):
    """The « NPA localité » line of a fiche's address."""

    postal_code: str | None = None
    city: str | None = None


class _Features(NamedTuple):
    """What the feature rows of a fiche tell."""

    property_type: PropertyType | None = None
    nb_rooms: float | None = None
    surface_m2: float | None = None


class BurgerScraper(HttpScraper):
    """Scrape every rental fiche listed in Burger's sitemap."""

    base_url = "https://www.burger-sa.ch/sitemap.php"
    slug = "burger"

    async def fetch_listings(self) -> list[Listing]:
        """Download the sitemap, then each rental fiche; skip failing or invalid ones."""
        listings: list[Listing] = []
        async with httpx.AsyncClient() as client:
            sitemap = await self._get(client, self.base_url)
            for node in self.listing_nodes(Selector(text=sitemap.text)):
                url = node.xpath("text()").get("")
                try:
                    fiche = await self._get(client, url)
                except httpx.HTTPError as error:
                    logger.warning("Fiche %s ignorée : %r", url, error)
                    continue
                listing = self._parse_or_skip(
                    partial(self.parse_listing, Selector(text=fiche.text), url)
                )
                if listing is not None:
                    listings.append(listing)
        return listings

    def listing_nodes(self, page: Selector) -> list[Selector]:
        """The sitemap entries of the rental fiches."""
        return page.xpath("//*[local-name()='loc'][contains(text(), '/fr/louer/')]")

    def parse_listing(self, node: Selector, url: str | None = None) -> Listing:
        """Extract the listing from a fiche page, known by `url` or by its canonical link."""
        url = url or node.css("link[rel=canonical]::attr(href)").get("")
        details = node.css("div.space-y-4.mt-6")
        address = [line.strip() for line in details.css("div.text-base::text").getall()]
        features = self.features(
            details.css("div.text-sm").xpath("normalize-space()").getall(), url
        )
        rent = self._get_rent(node)
        price_chf = parse_monthly_rent(rent, features.surface_m2)
        charges_chf = parse_charges(self._get_charges(node), rent, price_chf)
        # Burger shows the rent without charges: price_chf includes them.
        if price_chf is not None and charges_chf is not None:
            price_chf += charges_chf
        title = self._get_title(node)
        locality = self.locality(address)
        return Listing(
            external_url=url,
            external_id=url,
            title=title,
            property_type=features.property_type,
            price_chf=price_chf,
            charges_chf=charges_chf,
            floor=parse_floor(title),
            nb_rooms=features.nb_rooms,
            surface_m2=features.surface_m2,
            address=address[0] if address else None,
            postal_code=locality.postal_code,
            city=locality.city,
            description=node.css("div.prose").xpath("normalize-space()").get() or None,
            images=tuple(
                urljoin(self.base_url, src)
                for src in node.css("div.swiper-slide img::attr(data-src)").getall()
            ),
        )

    @staticmethod
    def features(rows: list[str], url: str) -> _Features:
        """Type, rooms and surface, each read from a whole feature row of its grammar.

        A row out of the known grammar is logged and ignored rather than guessed at:
        it means Burger changed its fiches, and the scraper must be revisited.
        « 0.0 pièces » means the number of rooms is unknown.
        """
        features = _Features()
        for row in rows:
            if (kind := _TYPE_ROW.fullmatch(row)) and (
                property_type := parse_property_type(kind["label"])
            ):
                features = features._replace(
                    property_type=property_type,
                    nb_rooms=parse_rooms(kind["rooms"]) or None,
                )
            elif surface := _SURFACE_ROW.fullmatch(row):
                features = features._replace(surface_m2=parse_surface(surface["m2"]))
            else:
                logger.warning("Fiche %s: unknown feature row %r ignored", url, row)
        return features

    @staticmethod
    def locality(address: list[str]) -> _Locality:
        """Postal code and town of the "NPA town" address line, e.g. "1204 Genève".

        Both are None without such a line.
        """
        for line in address[1:]:
            npa, _, town = line.partition(" ")
            if npa.isdigit() and town:
                return _Locality(postal_code=npa, city=town)
        return _Locality()

    def _get_rent(self, node: Selector) -> str | None:
        """Get the rent."""
        return node.xpath("//div[text()='Loyer']/following-sibling::div/text()").get()

    def _get_charges(self, node: Selector) -> str | None:
        """Get the charges."""
        return node.xpath("//div[text()='Charges']/following-sibling::div/text()").get()

    def _get_title(self, node: Selector) -> str:
        """Get the title."""
        return node.css("h1::text").get("")
