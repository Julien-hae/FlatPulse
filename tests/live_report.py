"""Helpers for fetching live catalogues and reporting their field coverage."""

import logging
from collections import Counter, defaultdict
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from typing import Literal, NamedTuple, get_args

import httpx

from flatpulse.common.models import Listing, PropertyType
from flatpulse.scrapers.base import SKIPPED_INVALID_LISTING, HttpScraper

logger = logging.getLogger(__name__)

FieldName = Literal[
    "price_chf", "surface_m2", "nb_rooms", "postal_code", "city", "canton", "images"
]
FILL_RATE_FIELDS: tuple[FieldName, ...] = get_args(FieldName)

# Source -> property type -> field -> minimum fill rate.
Thresholds = Mapping[str, Mapping[PropertyType, Mapping[FieldName, float]]]


class FillCount(NamedTuple):
    """How many listings of a group have a field filled, out of the group's size."""

    filled: int
    total: int

    @property
    def rate(self) -> float:
        """Share of the group with the field filled."""
        return self.filled / self.total


async def fetch_catalogues(
    scrapers: Sequence[HttpScraper],
) -> tuple[dict[str, list[Listing]], dict[str, str]]:
    """Fetch every catalogue in turn; a source down is recorded, the others go on.

    Each catalogue is logged as soon as it is fetched, so a network failure or a
    killed run later on does not lose the sources already audited.
    """
    catalogues: dict[str, list[Listing]] = {}
    errors: dict[str, str] = {}
    for scraper in scrapers:
        try:
            listings = await scraper.fetch_listings()
        except httpx.HTTPError as error:
            errors[scraper.slug] = f"{type(error).__name__}: {error}"
            logger.error("%s fetch failed: %s", scraper.slug, errors[scraper.slug])
            continue
        catalogues[scraper.slug] = listings
        source_catalogue = {scraper.slug: listings}
        logger.info(
            "Live catalogue %s (%d listings):\n%s\n\n%s",
            scraper.slug,
            len(listings),
            format_supply_distribution(source_catalogue),
            format_fill_rate_report(source_catalogue),
        )
    return catalogues, errors


@contextmanager
def skipped_listings() -> Iterator[list[str]]:
    """Collect the listings HttpScraper skips as invalid while the block runs.

    Records are matched on the `SKIPPED_INVALID_LISTING` format itself, not on its
    wording: other warnings of the scrapers (a fiche whose connection dropped) are
    not invalid listings.
    """
    messages: list[str] = []

    class _Collector(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            if record.msg == SKIPPED_INVALID_LISTING:
                messages.append(record.getMessage())

    base_logger = logging.getLogger("flatpulse.scrapers.base")
    collector = _Collector(level=logging.WARNING)
    base_logger.addHandler(collector)
    try:
        yield messages
    finally:
        base_logger.removeHandler(collector)


def format_supply_distribution(
    catalogues: Mapping[str, Sequence[Listing]],
) -> str:
    """Render the listing count by source, property type, and canton."""
    counts = Counter(
        (source, _type_name(listing.property_type), listing.canton or "unknown")
        for source, listings in catalogues.items()
        for listing in listings
    )
    rows = [
        "source | property_type | canton | listings",
        "--- | --- | --- | ---:",
    ]
    rows.extend(
        f"{source} | {property_type} | {canton} | {count}"
        for (source, property_type, canton), count in sorted(counts.items())
    )
    return "\n".join(rows)


def calculate_fill_rates(
    listings: Sequence[Listing],
    fields: Sequence[FieldName] = FILL_RATE_FIELDS,
) -> dict[PropertyType | None, dict[FieldName, FillCount]]:
    """Count the listings with each field filled, grouped by property type."""
    listings_by_type: dict[PropertyType | None, list[Listing]] = defaultdict(list)
    for listing in listings:
        listings_by_type[listing.property_type].append(listing)

    return {
        property_type: {
            field: FillCount(
                sum(_is_filled(getattr(listing, field)) for listing in typed_listings),
                len(typed_listings),
            )
            for field in fields
        }
        for property_type, typed_listings in listings_by_type.items()
    }


def format_fill_rate_report(
    catalogues: Mapping[str, Sequence[Listing]],
) -> str:
    """Render every source/type/field ratio, thresholds aside."""
    rows = [
        "source | property_type | field | filled | rate",
        "--- | --- | --- | ---: | ---:",
    ]
    for source in sorted(catalogues):
        counts_by_type = calculate_fill_rates(catalogues[source])
        if not counts_by_type:
            rows.append(f"{source} | — | — | 0/0 | —")
            continue
        for property_type in sorted(counts_by_type, key=_type_name):
            for field, count in counts_by_type[property_type].items():
                rows.append(
                    f"{source} | {_type_name(property_type)} | {field} | "
                    f"{count.filled}/{count.total} | {count.rate:.1%}"
                )
    return "\n".join(rows)


def fill_rate_shortfalls(
    catalogues: Mapping[str, Sequence[Listing]], thresholds: Thresholds
) -> list[str]:
    """Every source/type/field whose fill rate is under its threshold.

    A type with thresholds but no listing left is a shortfall too: the scraper lost
    it. A source missing from `catalogues` (fetch failed) is not reported here.
    """
    shortfalls: list[str] = []
    for source, by_type in thresholds.items():
        if source not in catalogues:
            continue
        counts_by_type = calculate_fill_rates(catalogues[source])
        for property_type, minimums in by_type.items():
            counts = counts_by_type.get(property_type)
            if counts is None:
                shortfalls.append(f"{source} | {property_type.value} : aucune annonce")
                continue
            shortfalls.extend(
                f"{source} | {property_type.value} | {field} : "
                f"{counts[field].rate:.1%} < {minimum:.0%}"
                for field, minimum in minimums.items()
                if counts[field].rate < minimum
            )
    return shortfalls


def _type_name(property_type: PropertyType | None) -> str:
    """The property type's value, `unknown` without one."""
    return property_type.value if property_type else "unknown"


def _is_filled(value: object | None) -> bool:
    """Treat absent scalar values and empty text/image collections as unfilled."""
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, tuple):
        return bool(value)
    return value is not None
