"""Swiss postal code -> canton, in memory: the rows, the lookup, the completion.

One row per (postal code, locality), with the canton holding most of the locality's
addresses, as swisstopo's official directory of localities gives them (open data,
« Source : Office fédéral de topographie swisstopo »).

Every scraper completes a canton the agency leaves out from the postal code
(`fill_missing_canton`, applied by `HttpScraper`), with a `CantonLookup` handed to it
at construction. Nothing here touches the network or the database: filling the
`postal_codes` table and reading it at startup is `flatpulse.postal_code_table`.
"""

import csv
import dataclasses
import io
import logging
from collections import defaultdict
from collections.abc import Iterable
from typing import NamedTuple

from flatpulse.common.models import Listing

logger = logging.getLogger(__name__)


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


class CantonLookup:
    """Postal code rows in memory: postal code -> casefolded locality -> canton."""

    def __init__(self, rows: Iterable[PostalCode]) -> None:
        """Index `rows` by postal code, then by locality, case aside."""
        self._localities: dict[str, dict[str, str]] = {}
        for row in rows:
            localities = self._localities.setdefault(row.postal_code, {})
            localities[row.locality.casefold()] = row.canton

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

    A canton written by the source is kept as is: the postal code only fills a gap.
    """
    if listing.canton is not None:
        return listing
    return dataclasses.replace(
        listing, canton=lookup.canton(listing.postal_code, listing.city)
    )
