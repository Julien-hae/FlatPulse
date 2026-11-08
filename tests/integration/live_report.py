"""Helpers for reporting live scraper field coverage."""

from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from typing import Literal

from flatpulse.common.models import Listing, PropertyType

FieldName = Literal["price_chf", "surface_m2", "nb_rooms", "postal_code", "images"]

FILL_RATE_FIELDS: tuple[FieldName, ...] = (
    "price_chf",
    "surface_m2",
    "nb_rooms",
    "postal_code",
    "images",
)

_FIELD_VALUES: dict[FieldName, Callable[[Listing], object | None]] = {
    "price_chf": lambda listing: listing.price_chf,
    "surface_m2": lambda listing: listing.surface_m2,
    "nb_rooms": lambda listing: listing.nb_rooms,
    "postal_code": lambda listing: listing.postal_code,
    "images": lambda listing: listing.images,
}


def calculate_fill_rates(
    listings: Sequence[Listing],
    fields: Sequence[FieldName] = FILL_RATE_FIELDS,
) -> dict[PropertyType | None, dict[FieldName, float]]:
    """Calculate non-empty field ratios grouped by listing property type."""
    listings_by_type: dict[PropertyType | None, list[Listing]] = defaultdict(list)
    for listing in listings:
        listings_by_type[listing.property_type].append(listing)

    return {
        property_type: {
            field: sum(
                _is_filled(_FIELD_VALUES[field](listing)) for listing in typed_listings
            )
            / len(typed_listings)
            for field in fields
        }
        for property_type, typed_listings in listings_by_type.items()
    }


def format_fill_rate_report(
    catalogues: Mapping[str, Sequence[Listing]],
) -> str:
    """Render every source/type/field ratio without applying pass/fail thresholds."""
    rows = [
        "source | property_type | field | filled | rate",
        "--- | --- | --- | ---: | ---:",
    ]

    for source in sorted(catalogues):
        listings = catalogues[source]
        rates_by_type = calculate_fill_rates(listings)
        if not rates_by_type:
            rows.append(f"{source} | — | — | 0/0 | —")
            continue

        for property_type in sorted(
            rates_by_type,
            key=lambda item: item.value if item is not None else "",
        ):
            typed_listings = [
                listing
                for listing in listings
                if listing.property_type == property_type
            ]
            for field, rate in rates_by_type[property_type].items():
                filled = sum(
                    _is_filled(_FIELD_VALUES[field](listing))
                    for listing in typed_listings
                )
                type_name = property_type.value if property_type else "unknown"
                rows.append(
                    f"{source} | {type_name} | {field} | "
                    f"{filled}/{len(typed_listings)} | {rate:.1%}"
                )

    return "\n".join(rows)


def _is_filled(value: object | None) -> bool:
    """Treat absent scalar values and empty text/image collections as unfilled."""
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, tuple):
        return bool(value)
    return value is not None
