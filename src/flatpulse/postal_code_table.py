"""The `postal_codes` table: filled from swisstopo, read once at startup.

The table (`sql/schema.sql`) is refreshed, or filled on a new database, by running
this module:

    python -m flatpulse.postal_code_table

The pipeline reads it once per process with `load_canton_lookup()` and hands the
lookup to the scrapers. The rows and the lookup themselves, which need neither the
network nor the database, are `flatpulse.common.postal_codes`.
"""

import asyncio
import io
import logging
import os
import zipfile

import httpx

from flatpulse import db
from flatpulse.common.postal_codes import CantonLookup, PostalCode, rows_from_swisstopo

logger = logging.getLogger(__name__)

SWISSTOPO_LOCALITIES_URL = (
    "https://data.geo.admin.ch/ch.swisstopo-vd.ortschaftenverzeichnis_plz/"
    "ortschaftenverzeichnis_plz/ortschaftenverzeichnis_plz_2056.csv.zip"
)
REFRESH_COMMAND = "python -m flatpulse.postal_code_table"


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


async def load_canton_lookup() -> CantonLookup:
    """Read the `postal_codes` table, once, at startup.

    Raises:
        RuntimeError: The table is empty, so no canton could ever be completed.
    """
    rows = await db.get_postal_codes()
    if not rows:
        raise RuntimeError(
            f"The postal_codes table is empty: fill it with `{REFRESH_COMMAND}`"
        )
    return CantonLookup(PostalCode(**row) for row in rows)


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
