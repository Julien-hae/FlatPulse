"""Swiss postal code -> canton table, shaped as the `postal_codes` SQL table.

`sql/postal_codes.csv` has the columns of that table (`sql/schema.sql`): one row per
(postal code, locality), with the canton holding most of the locality's addresses. It
is built from swisstopo's official directory of localities (open data, « Source :
Office fédéral de topographie swisstopo ») and refreshed by running this module:

    python -m flatpulse.common.postal_codes

`read_table()` is the only reader: moving the lookup to PostgreSQL (#133) replaces it
with a SELECT, and `COPY postal_codes FROM … CSV HEADER` loads the file as is.
"""

import csv
import io
import logging
import os
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import NamedTuple

import httpx

logger = logging.getLogger(__name__)

SWISSTOPO_LOCALITIES_URL = (
    "https://data.geo.admin.ch/ch.swisstopo-vd.ortschaftenverzeichnis_plz/"
    "ortschaftenverzeichnis_plz/ortschaftenverzeichnis_plz_2056.csv.zip"
)
# src/flatpulse/common/postal_codes.py -> the repository's sql/ folder.
TABLE_PATH = Path(__file__).resolve().parents[3] / "sql" / "postal_codes.csv"
COLUMNS = ("postal_code", "locality", "canton")


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

    Raises httpx.HTTPError when swisstopo is unreachable or answers an error.
    """
    response = httpx.get(SWISSTOPO_LOCALITIES_URL, timeout=30, follow_redirects=True)
    response.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        [name] = [item for item in archive.namelist() if item.endswith(".csv")]
        return rows_from_swisstopo(archive.read(name).decode("utf-8-sig"))


def write_table(rows: list[PostalCode], path: Path = TABLE_PATH) -> None:
    """Write `rows` with the SQL columns, replacing `path` only once fully written."""
    partial = path.with_suffix(".csv.partial")
    with partial.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(COLUMNS)
        writer.writerows(rows)
    os.replace(partial, path)


def read_table(path: Path = TABLE_PATH) -> dict[str, dict[str, str]]:
    """Postal code -> casefolded locality -> canton, as read from the table."""
    table: dict[str, dict[str, str]] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            localities = table.setdefault(row["postal_code"], {})
            localities[row["locality"].casefold()] = row["canton"]
    return table


def main(path: Path = TABLE_PATH) -> None:
    """Refresh the table from swisstopo; swisstopo down leaves it as it was."""
    rows = download_swisstopo()
    write_table(rows, path)
    logger.info(
        "Postal code table refreshed from swisstopo: %d rows in %s", len(rows), path
    )


if __name__ == "__main__":
    main()
