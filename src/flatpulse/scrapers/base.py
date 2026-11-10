"""Base classes defining the contract every listing scraper must follow.

Agencies publish their listings in one of two shapes, each with its base class:

- `CatalogueScraper`: one document holds every listing (Naef's JSON payload);
- `FicheScraper`: an index names the fiches, and each fiche is one listing
  (Burger's sitemap, Comptoir's paginated catalogue).

Both share `HttpScraper`: the limiter every request waits for, and the building of
a `Listing` that skips an invalid one instead of losing the poll.
"""

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from functools import partial

import httpx
from parsel import Selector

from flatpulse.common.models import Listing
from flatpulse.common.postal_codes import CantonLookup, fill_missing_canton
from flatpulse.scrapers.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

# Logged for each listing skipped as invalid; the live audit (#119) counts them by it.
SKIPPED_INVALID_LISTING = "Skipped invalid listing: %s"


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
        """
        self.rate_limiter = rate_limiter
        self.canton_lookup = canton_lookup

    async def _get(self, client: httpx.AsyncClient, url: str) -> httpx.Response:
        """GET `url` once the limiter grants this source a token; raise on HTTP error.

        Every request of a scraper goes through here, so none escapes the limiter.
        """
        await self.rate_limiter.acquire(self.slug)
        response = await client.get(url)
        response.raise_for_status()
        return response

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
    """Scraper of a source read fiche by fiche: an index names them, each is a listing."""

    @abstractmethod
    async def fiche_urls(self, client: httpx.AsyncClient) -> list[str]:
        """URLs of every fiche the source publishes, read from its index through `_get`."""
        raise NotImplementedError

    @abstractmethod
    def parse_fiche(self, node: Selector, url: str) -> Listing:
        """Parse `node`, the fiche page downloaded from `url`, into a Listing."""
        raise NotImplementedError

    async def fetch_listings(self) -> list[Listing]:
        """Read the index, then each fiche; skip failing or invalid ones.

        A fiche that fails to download is logged and skipped: one dropped
        connection must not lose the other fiches. The index failing is the
        source failing: its error is raised.
        """
        listings: list[Listing] = []
        async with httpx.AsyncClient() as client:
            for url in await self.fiche_urls(client):
                try:
                    response = await self._get(client, url)
                except httpx.HTTPError as error:
                    logger.warning("Fiche %s skipped: %r", url, error)
                    continue
                page = Selector(text=response.text)
                listing = self._build_or_skip(partial(self.parse_fiche, page, url))
                if listing is not None:
                    listings.append(listing)
        return listings
