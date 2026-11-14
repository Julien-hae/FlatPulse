"""Scraper for Comptoir Immobilier: the catalogue lists the fiches, each fiche is a listing.

The catalogue is sorted newest first (checked against the RSS `pubDate`s on
14.11.2026, `docs/spike-agencies.md`): a poll reads its first page, and goes on
only while a page shows a card it does not know. The whole catalogue is walked
at the first poll, then once an hour.
"""

import time
from collections.abc import Callable

import httpx
from parsel import Selector, SelectorList

from flatpulse.common.models import Listing
from flatpulse.common.postal_codes import CantonLookup
from flatpulse.common.utils import (
    canton_code,
    parse_charges,
    parse_floor,
    parse_monthly_rent,
    parse_property_type,
    parse_rooms,
    parse_surface,
)
from flatpulse.scrapers.base import FicheScraper
from flatpulse.scrapers.rate_limiter import RateLimiter

# Only a walk of every page sees a card that left the catalogue, or one that
# changed beyond the pages a short poll reads.
FULL_WALK_EVERY_S = 3600.0


class ComptoirScraper(FicheScraper):
    """Scrape every rental fiche of the Comptoir Immobilier catalogue."""

    base_url = "https://comptoir-immo.ch/location/"
    slug = "comptoir"

    def __init__(
        self,
        rate_limiter: RateLimiter,
        canton_lookup: CantonLookup,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Read the time, in seconds, from `clock`: it dates the full walks."""
        super().__init__(rate_limiter, canton_lookup)
        self._clock = clock
        self._last_full_walk: float | None = None

    @staticmethod
    def nb_pages(page: Selector) -> int:
        """Return the number of pages announced by the pagination links."""
        numbers = [
            int(text.strip())
            for text in page.css("a.page-number.page-numbers::text").getall()
            if text.strip().isdigit()
        ]
        return max(numbers, default=1)

    def parse_fiche(self, node: Selector, url: str) -> Listing:
        """Extract the listing from a fiche, mostly from its « Détails » table.

        The fiche's canonical link is its published URL, kept rather than `url`,
        the card's link it was downloaded from; a fiche without one is invalid.
        """
        url = node.css("link[rel=canonical]::attr(href)").get("")
        city, _, canton = (self._text(node.css("h1 + h2")) or "").partition(", ")
        surface_m2 = parse_surface(self._detail(node, "Surface"))
        price_chf = parse_monthly_rent(
            self._text(node.css("h1 ~ .heading-3")), surface_m2
        )
        # The header rent already includes the charges of the « Détails » table.
        charges_chf = parse_charges(
            self._detail(node, "Charges"), self._detail(node, "Loyer"), price_chf
        )
        property_label = self._detail(node, "Type de bien")
        h1 = node.css("h1")
        return Listing(
            external_url=url,
            external_id=url.rstrip("/").rsplit("/", 1)[-1],
            # An empty <h1> (some parkings) is named by the type; no <h1> at all is a
            # redesign, left to fail validation so that the live audit (#119) sees it.
            title=self._text(h1) or (property_label if h1 else None) or "",
            property_type=parse_property_type(property_label),
            price_chf=price_chf,
            charges_chf=charges_chf,
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

    async def fiche_versions(self, client: httpx.AsyncClient) -> dict[str, str | None]:
        """The fiches of the catalogue, versioned by their card.

        A short poll reads the first page, then the next one as long as the page
        just read shows a card whose fiche is not remembered: with nothing
        published, one request. The fiches of the pages it did not read keep
        the version they are remembered with.

        The first poll, then one poll an hour, walks every page: the fiches it
        returns are the catalogue's, so a card that left it is forgotten.
        """
        now = self._clock()
        full_walk = (
            self._last_full_walk is None
            or now - self._last_full_walk >= FULL_WALK_EVERY_S
        )
        page = await self._get_page(client, f"{self.base_url}?page=1")
        last = self.nb_pages(page)
        cards = self._cards(page)
        walked = dict(cards)
        number = 1
        while number < last and (full_walk or cards.keys() - self._fiches.keys()):
            number += 1
            page = await self._get_page(client, f"{self.base_url}?page={number}")
            cards = self._cards(page)
            walked |= cards
        if not full_walk:
            return {url: fiche.version for url, fiche in self._fiches.items()} | walked
        self._last_full_walk = now
        return walked

    @staticmethod
    def _cards(page: Selector) -> dict[str, str | None]:
        """The fiches carded on a catalogue page: their URL, and the card's text.

        A card shows the rent, the title, the type, the rooms, the surface and the
        town: its text moves when one of them does.
        """
        return {
            url: card.xpath("normalize-space()").get()
            for card in page.css("article.teaser--property_for_rent")
            if (url := card.css("a:has(h2)::attr(href)").get())
        }

    async def _get_page(self, client: httpx.AsyncClient, url: str) -> Selector:
        """GET `url` through the limiter (Crawl-delay of 10 s), and parse it."""
        return Selector(text=(await self._get(client, url)).text)
