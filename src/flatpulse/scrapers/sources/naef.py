"""Scraper for Naef Immobilier, which exposes its whole catalogue as one JSON payload."""

from typing import Any

from parsel import Selector

from flatpulse.common.utils import parse_rooms, parse_surface, parse_swiss_price
from flatpulse.scrapers.base import HttpScraper


class NaefScraper(HttpScraper):
    """Scrape rental listings from the Naef `get_all_props` endpoint."""

    base_url = (
        "https://www.naef.ch/wp-admin/admin-ajax.php?action=get_all_props&type=Location"
    )

    def listing_nodes(self, page: Selector) -> list[Selector]:
        """Return one JSON node per property in the payload."""
        return list(page.jmespath("props[*]"))

    def parse_listing(self, node: Selector) -> dict[str, Any]:
        """Extract the listing fields from a property node."""
        return {
            "external_id": self._text(node, "no_dossier"),
            "external_url": self._text(node, "link"),
            "title": self._text(node, "intitule_plaquette"),
            "price_chf": self._parse_naef_price(node),
            "nb_rooms": parse_rooms(self._text(node, "nb_pieces")),
            "surface_m2": parse_surface(self._text(node, "surface_habitable")),
            "city": self._text(node, "adresse_localite"),
            "images": node.jmespath("imgs[*]").getall(),
        }

    @staticmethod
    def _text(node: Selector, key: str) -> str | None:
        """Return the value at `key` as a string, or None when absent or empty."""
        value = node.jmespath(key).get()
        return str(value) if value not in (None, "") else None

    @classmethod
    def _parse_naef_price(cls, node: Selector) -> int | None:
        """Parse the monthly rent into centimes; None when absent or on request."""
        if node.jmespath("loyer_sur_demande").get() == "oui":
            return None
        return parse_swiss_price(cls._text(node, "loyer_mensuel_brut"))
