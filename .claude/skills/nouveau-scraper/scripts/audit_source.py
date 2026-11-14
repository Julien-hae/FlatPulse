"""Live audit of one source: what its scraper really extracts from the whole offer.

    FLATPULSE_LIVE=1 python .claude/skills/nouveau-scraper/scripts/audit_source.py SLUG

The full audit (tests/integration/test_live_sources.py) polls every agency, for more
than an hour: to look at one new source, that is traffic the others did not ask for.
This runs the same fetch and the same report for one source only, at the rate
registered for it in `RATE_LIMITS_RPM`, and proposes its `MIN_FILL_RATE` by the
rule written there: the measure less 10 points, rounded down to 5 %, for the types
with at least 20 listings and the rates above 0 %.

This is real traffic at the agency: one run, not a loop.
"""

import argparse
import asyncio
import datetime
import logging
import os
import sys
import time
from pathlib import Path

ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / "pyproject.toml").exists()
)
# `tests` is a package of the repository, not an installed one: a script run by its
# path only sees it once the root is on the path, hence the imports below it.
sys.path.insert(0, str(ROOT))

from tests.integration.test_live_sources import (  # noqa: E402
    RATE_LIMITS_RPM,
    SCRAPER_CLASSES,
)
from tests.live_report import (  # noqa: E402
    FieldName,
    calculate_fill_rates,
    fetch_catalogues,
    format_fill_rate_report,
    format_supply_distribution,
    skipped_listings,
)

from flatpulse.common.models import Listing, PropertyType  # noqa: E402
from flatpulse.common.postal_codes import CantonLookup  # noqa: E402
from flatpulse.postal_code_table import download_swisstopo  # noqa: E402
from flatpulse.scrapers.rate_limiter import RateLimiter  # noqa: E402

# The fields the existing thresholds watch; `city` is reported, never thresholded.
THRESHOLD_FIELDS: tuple[FieldName, ...] = (
    "price_chf",
    "surface_m2",
    "nb_rooms",
    "postal_code",
    "canton",
    "images",
)
MIN_LISTINGS = 20
MARGIN_POINTS = 10
STEP_POINTS = 5


def main() -> None:
    """Fetch the catalogue of one source and print its audit."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("slug")
    slug: str = parser.parse_args().slug
    if os.environ.get("FLATPULSE_LIVE") != "1":
        raise SystemExit("FLATPULSE_LIVE=1 requis : c'est du trafic réel chez la régie")
    scraper_class = next((c for c in SCRAPER_CLASSES if c.slug == slug), None)
    if scraper_class is None or slug not in RATE_LIMITS_RPM:
        raise SystemExit(
            f"{slug} n'est pas enregistré : l'ajouter à SCRAPER_CLASSES et, avec le "
            "débit du spike, à RATE_LIMITS_RPM (tests/integration/test_live_sources.py)"
        )
    # stderr keeps each request and each warning of the scraper (unknown label,
    # unknown postal code): the progress of a long run, and findings. The tables
    # fetch_catalogues logs are printed once, below, on stdout.
    logging.getLogger("tests.live_report").setLevel(logging.WARNING)
    scraper = scraper_class(
        rate_limiter=RateLimiter({slug: RATE_LIMITS_RPM[slug]}),
        canton_lookup=CantonLookup(download_swisstopo()),
    )
    started = time.monotonic()
    with skipped_listings() as skipped:
        catalogues, errors = asyncio.run(fetch_catalogues([scraper]))
    now = datetime.datetime.now(tz=datetime.UTC)
    print(f"## Run du {now:%d.%m.%Y, %H:%M} UTC — {slug}")
    print(f"- Durée : {time.monotonic() - started:.0f} s à {RATE_LIMITS_RPM[slug]} rpm")
    if slug in errors:
        raise SystemExit(f"- Échec du fetch : {errors[slug]}")
    listings = catalogues[slug]
    unknown_canton = sum(listing.canton is None for listing in listings)
    print(f"- Volume : {len(listings)} annonces, canton inconnu : {unknown_canton}")
    print(f"- Annonces ignorées comme invalides : {len(skipped)}")
    for message in skipped:
        print(f"  - {message}")
    print(f"\n{format_supply_distribution(catalogues)}")
    print(f"\n{format_fill_rate_report(catalogues)}")
    print(f"\n{proposed_thresholds(slug, listings)}")
    if skipped or not listings:
        raise SystemExit(1)


def proposed_thresholds(slug: str, listings: list[Listing]) -> str:
    """The `MIN_FILL_RATE` entry of `slug`, ready to paste, from this run."""
    lines = [f'    "{slug}": {{']
    without: list[str] = []
    counts_by_type = calculate_fill_rates(listings, THRESHOLD_FIELDS)
    for property_type in sorted(PropertyType):
        counts = counts_by_type.get(property_type)
        if counts is None:
            continue
        total = next(iter(counts.values())).total
        if total < MIN_LISTINGS:
            without.append(f"{property_type.value} ({total})")
            continue
        lines.append(f"        PropertyType.{property_type.name}: {{")
        for field, count in counts.items():
            # In whole numbers: 0.95 - 0.10 is not 0.85 in floating point.
            steps = (count.filled * 100 - MARGIN_POINTS * count.total) // (
                STEP_POINTS * count.total
            )
            if steps > 0:
                lines.append(f'            "{field}": {steps * STEP_POINTS / 100:g},')
        lines.append("        },")
    lines.append("    },")
    untyped = sum(listing.property_type is None for listing in listings)
    notes = [
        "# MIN_FILL_RATE proposé (mesure moins 10 points, arrondie à 5 % en dessous) :",
        *lines,
        f"# Sans seuil, moins de {MIN_LISTINGS} annonces : {', '.join(without) or '—'}",
        f"# Annonces sans property_type : {untyped}",
    ]
    return "\n".join(notes)


if __name__ == "__main__":
    main()
