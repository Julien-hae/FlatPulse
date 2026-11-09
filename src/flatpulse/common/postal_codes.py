"""Swiss postal code -> canton: the `postal_codes` table, its refresh and its lookup.

The table (`sql/schema.sql`) has one row per (postal code, locality), with the canton
holding most of the locality's addresses. It is built from swisstopo's official
directory of localities (open data, « Source : Office fédéral de topographie
swisstopo ») and refreshed, or filled on a new database, by running this module:

    python -m flatpulse.common.postal_codes

Scrapers report the canton only when the agency writes it. The pipeline completes a
missing one from the postal code with `fill_missing_canton`, using a `CantonLookup`
loaded once per process.
"""

import asyncio
import csv
import dataclasses
import io
import logging
import os
import zipfile
from collections import defaultdict
from collections.abc import Iterable
from typing import NamedTuple, Self

import httpx

from flatpulse import db
from flatpulse.common.models import Listing

logger = logging.getLogger(__name__)

SWISSTOPO_LOCALITIES_URL = (
    "https://data.geo.admin.ch/ch.swisstopo-vd.ortschaftenverzeichnis_plz/"
    "ortschaftenverzeichnis_plz/ortschaftenverzeichnis_plz_2056.csv.zip"
)
REFRESH_COMMAND = "python -m flatpulse.common.postal_codes"


class PostalCode(NamedTuple):
    """One row of the table: a locality of a postal code, and its canton."""

    postal_code: str
    locality: str
    canton: str


def rows_from_swisstopo(text: str) -> list[PostalCode]:
    """Table rows from the text of swisstopo's directory (`;`-separated CSV).

    The directory lists a locality once per municipality it spans, with the share of
    its addresses there (`Adressenanteil`): the locality keeps the canton holding the
    largest share. Rows without a canton (Liechtenstein) are left out.
    """
    shares: defaultdict[tuple[str, str], defaultdict[str, float]] = defaultdict(
        lambda: defaultdict(float)
    )
    for row in csv.DictReader(io.StringIO(text), delimiter=";"):
        if canton := row["Kantonskürzel"]:
            share = float(row["Adressenanteil"].removesuffix("%"))
            shares[row["PLZ4"], row["Ortschaftsname"]][canton] += share
    return sorted(
        PostalCode(postal_code, locality, max(by_canton, key=by_canton.__getitem__))
        for (postal_code, locality), by_canton in shares.items()
    )


def download_swisstopo() -> list[PostalCode]:
    """Download swisstopo's directory of localities and turn it into table rows.

    Raises:
        httpx.HTTPError: swisstopo is unreachable or answers an error.
    """
    response = httpx.get(SWISSTOPO_LOCALITIES_URL, timeout=30, follow_redirects=True)
    response.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        [name] = [item for item in archive.namelist() if item.endswith(".csv")]
        return rows_from_swisstopo(archive.read(name).decode("utf-8-sig"))


async def refresh() -> int:
    """Replace the table with swisstopo's directory; return the number of rows.

    The download comes first: swisstopo down raises `httpx.HTTPError` before the
    table is touched, and it keeps its last version.
    """
    rows = download_swisstopo()
    await db.replace_postal_codes(rows)
    return len(rows)


class CantonLookup:
    """The postal code table in memory: postal code -> casefolded locality -> canton."""

    def __init__(self, rows: Iterable[PostalCode]) -> None:
        """Index `rows` by postal code, then by locality, case aside."""
        self._localities: dict[str, dict[str, str]] = {}
        for row in rows:
            localities = self._localities.setdefault(row.postal_code, {})
            localities[row.locality.casefold()] = row.canton

    @classmethod
    async def load(cls) -> Self:
        """Read the `postal_codes` table, once, at startup.

        Raises:
            RuntimeError: The table is empty, so no canton could ever be completed.
        """
        rows = await db.get_postal_codes()
        if not rows:
            raise RuntimeError(
                f"The postal_codes table is empty: fill it with `{REFRESH_COMMAND}`"
            )
        return cls(PostalCode(**row) for row in rows)

    def canton(self, postal_code: str | None, locality: str | None) -> str | None:
        """Canton of a Swiss postal code, the locality deciding a shared one.

        A code within one canton needs no locality: « 1206 » is GE. A code shared by
        cantons is decided by its locality, case aside: « 1290 Versoix » is GE,
        « 1290 Chavannes-des-Bois » VD. A shared code without a known locality, or
        an unknown code, gives None and a WARNING: a canton is never guessed.
        """
        if not postal_code:
            return None
        localities = self._localities.get(postal_code)
        if localities is None:
            logger.warning("Unknown postal code %r", postal_code)
            return None
        cantons = set(localities.values())
        if len(cantons) == 1:
            return cantons.pop()
        canton = localities.get((locality or "").casefold())
        if canton is None:
            logger.warning(
                "Postal code %r spans cantons %s, locality %r decides none",
                postal_code,
                sorted(cantons),
                locality,
            )
        return canton


def fill_missing_canton(listing: Listing, lookup: CantonLookup) -> Listing:
    """`listing` with its canton completed from its postal code and city.

    The pipeline step between dedup and enrichment: a canton written by the source
    is kept as is, the postal code only fills a gap.
    """
    if listing.canton is not None:
        return listing
    return dataclasses.replace(
        listing, canton=lookup.canton(listing.postal_code, listing.city)
    )


async def _refresh_database(database_url: str) -> int:
    """Refresh the table of the database at `database_url`."""
    await db.open_pool(database_url)
    try:
        return await refresh()
    finally:
        await db.close_pool()


def main() -> None:
    """Refresh the table from swisstopo; swisstopo down leaves it as it was."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit(
            "DATABASE_URL is missing: the postal code table is written to PostgreSQL "
            "(see .env.example)"
        )
    count = asyncio.run(_refresh_database(database_url))
    logger.info("Postal code table refreshed from swisstopo: %d rows", count)


if __name__ == "__main__":
    main()
