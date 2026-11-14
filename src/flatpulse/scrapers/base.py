"""Base classes defining the contract every listing scraper must follow.

Agencies publish their listings in one of two shapes, each with its base class:

- `CatalogueScraper`: one document holds every listing (Naef's JSON payload);
- `FicheScraper`: an index names the fiches, and each fiche is one listing
  (Burger's sitemap, Comptoir's paginated catalogue).

Both share `HttpScraper`: the limiter every request waits for, the building of a
`Listing` that skips an invalid one instead of losing the poll, and the cache that
spares a fiche already read from being downloaded again.
"""

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from functools import partial
from typing import NamedTuple

import httpx
from parsel import Selector

from flatpulse.common.models import Listing
from flatpulse.common.postal_codes import CantonLookup, fill_missing_canton
from flatpulse.scrapers.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

# Logged for each listing skipped as invalid; the live audit (#119) counts them by it.
SKIPPED_INVALID_LISTING = "Skipped invalid listing: %s"


class _CachedFiche(NamedTuple):
    """A fiche as last read, and the version its source gave it then."""

    version: str | None
    listing: Listing


class AbstractScraper(ABC):
    """Contract every scraper must implement, regardless of source technology."""

    @abstractmethod
    async def fetch_listings(self) -> list[Listing]:
        """Fetch and return listings as a list of Listing."""
        raise NotImplementedError

    async def run(self) -> list[Listing]:
        """Orchestrate a scrape; the pace is set request by request by the limiter."""
        return await self.fetch_listings()


class HttpScraper(AbstractScraper):
    """What every HTTP scraper shares: paced requests and guarded listing building.

    Not subclassed by a source directly: a source is a `CatalogueScraper` or a
    `FicheScraper`.
    """

    base_url: str
    slug: str

    def __init__(self, rate_limiter: RateLimiter, canton_lookup: CantonLookup) -> None:
        """Keep the request limiter of this source and the postal code table.

        The limiter paces every request of `slug`; the table completes a canton the
        source leaves out. Neither has a default: the pipeline builds both.

        The fiches read are remembered in memory, by URL: the pipeline keeps one
        scraper per source from poll to poll, and a restart reads them all again.
        """
        self.rate_limiter = rate_limiter
        self.canton_lookup = canton_lookup
        self._fiches: dict[str, _CachedFiche] = {}

    async def _get(self, client: httpx.AsyncClient, url: str) -> httpx.Response:
        """GET `url` once the limiter grants this source a token; raise on HTTP error.

        Every request of a scraper goes through here, so none escapes the limiter.
        """
        await self.rate_limiter.acquire(self.slug)
        response = await client.get(url)
        response.raise_for_status()
        return response

    async def _cached_fiche(
        self,
        client: httpx.AsyncClient,
        url: str,
        version: str | None,
        parse: Callable[[Selector], Listing],
    ) -> Listing | None:
        """The listing of the fiche at `url`, downloaded only if `version` is new.

        `version` is what the source tells of the fiche without it (a catalogue
        card, a `lastmod`): unchanged since the last read, the listing remembered
        is returned and nothing is requested. A fiche never read, a version that
        moved, or no version at all (None), costs one paced GET, parsed by `parse`.

        A fiche that fails to download is logged and stays as it was last read,
        None if it never was; its version is not remembered, so the next poll
        tries again. One dropped connection must neither lose the other fiches
        nor make a listing vanish. An invalid fiche is skipped, and retried too.
        """
        cached = self._fiches.get(url)
        if cached is not None and version is not None and cached.version == version:
            return cached.listing
        try:
            response = await self._get(client, url)
        except httpx.HTTPError as error:
            logger.warning("Fiche %s not downloaded: %r", url, error)
            return cached.listing if cached is not None else None
        listing = self._build_or_skip(partial(parse, Selector(text=response.text)))
        if listing is not None:
            self._fiches[url] = _CachedFiche(version, listing)
        return listing

    def _build_or_skip(self, parse: Callable[[], Listing]) -> Listing | None:
        """The listing `parse` returns, its canton completed; None if it is invalid.

        A canton the source does not write is completed from the postal code and
        city, here, so every scraper gets it without writing a line. An invalid
        listing is logged and skipped, the poll goes on: its ValueError names the
        faulty field and the listing's URL.

        A parser that crashes on a page it did not expect is skipped the same way,
        logged as an error with its traceback: a bug on one listing must not lose
        the others, nor go unseen.
        """
        try:
            return fill_missing_canton(parse(), self.canton_lookup)
        except ValueError as error:
            logger.warning(SKIPPED_INVALID_LISTING, error)
        except Exception as error:
            logger.exception(SKIPPED_INVALID_LISTING, repr(error))
        return None


class CatalogueScraper(HttpScraper):
    """Scraper of a source whose single document, at `base_url`, holds every listing."""

    @abstractmethod
    def listing_nodes(self, page: Selector) -> list[Selector]:
        """Return one Selector per listing found in the parsed document."""
        raise NotImplementedError

    @abstractmethod
    def parse_listing(self, node: Selector) -> Listing:
        """Parse one node of `listing_nodes` into a Listing."""
        raise NotImplementedError

    async def fetch_listings(self) -> list[Listing]:
        """Download the document and parse each of its nodes; skip invalid ones."""
        async with httpx.AsyncClient() as client:
            response = await self._get(client, self.base_url)
        listings: list[Listing] = []
        for node in self.listing_nodes(Selector(text=response.text)):
            listing = self._build_or_skip(partial(self.parse_listing, node))
            if listing is not None:
                listings.append(listing)
        return listings


class FicheScraper(HttpScraper):
    """Scraper of a source read fiche by fiche: an index names them, each is a listing.

    A poll reads the index, then only the fiches the index shows as new or changed.
    """

    @abstractmethod
    async def fiche_versions(self, client: httpx.AsyncClient) -> dict[str, str | None]:
        """Every fiche the source publishes: its URL, and its version in the index.

        The index is read through `_get`. The version is whatever it tells of a
        fiche that moves when the fiche does; None when it tells nothing.
        """
        raise NotImplementedError

    @abstractmethod
    def parse_fiche(self, node: Selector, url: str) -> Listing:
        """Parse `node`, the fiche page downloaded from `url`, into a Listing."""
        raise NotImplementedError

    async def fetch_listings(self) -> list[Listing]:
        """Read the index, then each new or changed fiche; return every listing.

        The listings of the index all come out, read now or remembered; a fiche
        that left the index is forgotten. The index failing is the source
        failing: its error is raised.
        """
        listings: list[Listing] = []
        async with httpx.AsyncClient() as client:
            versions = await self.fiche_versions(client)
            for url, version in versions.items():
                listing = await self._cached_fiche(
                    client, url, version, partial(self.parse_fiche, url=url)
                )
                if listing is not None:
                    listings.append(listing)
        self._fiches = {
            url: self._fiches[url] for url in versions if url in self._fiches
        }
        return listings
