"""Scraper for Naef Immobilier, which exposes its whole catalogue as one JSON payload."""

import logging

from parsel import Selector

from flatpulse.common.models import Listing, PropertyType
from flatpulse.common.utils import (
    canton_code,
    parse_monthly_rent,
    parse_rooms,
    parse_surface,
    parse_swiss_price,
)
from flatpulse.scrapers.base import HttpScraper

logger = logging.getLogger(__name__)
TYPE_CODE_TO_PROPERTY = {
    "APP": PropertyType.APARTMENT,
    "PARC": PropertyType.PARKING,
    "MAI": PropertyType.HOUSE,
    "LCO": PropertyType.COMMERCIAL,
}


class NaefScraper(HttpScraper):
    """Scrape rental listings from the Naef `get_all_props` endpoint."""

    base_url = (
        "https://www.naef.ch/wp-admin/admin-ajax.php?action=get_all_props&type=Location"
    )
    slug = "naef"

    def listing_nodes(self, page: Selector) -> list[Selector]:
        """Return one JSON node per property in the payload."""
        return list(page.jmespath("props[*]"))

    def parse_listing(self, node: Selector) -> Listing:
        """Extract the listing fields from a property node."""
        rent = (
            None
            if node.jmespath("loyer_sur_demande").get() == "oui"
            else self._text(node, "loyer_mensuel_brut")
        )
        surface_m2 = self._surface_m2(node)
        price_chf = parse_monthly_rent(rent, surface_m2)
        return Listing(
            external_id=self._text(node, "no_dossier") or "",
            external_url=self._text(node, "link") or "",
            title=self._text(node, "intitule_plaquette")
            or self._text(node, "type_designation_fr")
            or "",
            price_chf=price_chf,
            nb_rooms=parse_rooms(self._text(node, "nb_pieces")) or None,
            surface_m2=surface_m2,
            city=self._text(node, "adresse_localite"),
            images=self._images(node),
            property_type=self._property_type(node),
            postal_code=self._text(node, "npa"),
            canton=self._canton(node),
            charges_chf=self._charges_chf(node),
        )

    @staticmethod
    def _text(node: Selector, key: str) -> str | None:
        """Return the value at `key` as a string, or None when absent or empty."""
        value = node.jmespath(key).get()
        return str(value) if value not in (None, "") else None

    def _property_type(self, node: Selector) -> PropertyType | None:
        """Return property type."""
        type_code = self._text(node, "type_code")
        if not type_code:
            return None
        if type_code not in TYPE_CODE_TO_PROPERTY:
            logger.warning(
                "Unknown Naef type_code %r for %s",
                type_code,
                self._text(node, "no_dossier"),
            )
        return TYPE_CODE_TO_PROPERTY.get(type_code)

    def _canton(self, node: Selector) -> str | None:
        """Return canton abbreviation."""
        return canton_code(self._text(node, "adresse_canton"))

    def _charges_chf(self, node: Selector) -> int | None:
        """Return charges in CHF."""
        if node.jmespath("loyer_sur_demande").get() == "oui":
            return None
        net = parse_swiss_price(self._text(node, "loyer_mensuel_net"))
        gross = parse_swiss_price(self._text(node, "loyer_mensuel_brut"))
        if net is None or gross is None:
            return None

        charges = gross - net
        return charges if charges > 0 else None

    def _surface_m2(self, node: Selector) -> float | None:
        """Return surface in m2."""
        return parse_surface(self._text(node, "surface_habitable")) or None

    def _images(self, node: Selector) -> tuple[str, ...]:
        """Return image URLs from a list or indexed object in payload order."""
        return tuple(node.jmespath("imgs[*] || imgs.*").getall())
