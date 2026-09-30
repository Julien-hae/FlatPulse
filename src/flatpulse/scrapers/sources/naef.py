"""Scraper for Naef Immobilier.

Naef renders its listings in JavaScript, but the whole catalogue is served as JSON by
a WordPress AJAX endpoint (see `docs/spike-agencies.md`). `parsel` detects the JSON
body on its own, so the `HttpScraper` fetch/parse pipeline is reused unchanged.
"""

from typing import Any, cast

from parsel import Selector

from flatpulse.common.utils import parse_swiss_price
from flatpulse.scrapers.base import HttpScraper


class NaefScraper(HttpScraper):
    """Scraper for the Naef Immobilier rental catalogue."""

    base_url = (
        "https://www.naef.ch/wp-admin/admin-ajax.php?action=get_all_props&type=Location"
    )

    def listing_nodes(self, page: Selector) -> list[Selector]:
        """Return one Selector per property of the JSON payload."""
        return list(page.jmespath("props[*]"))

    def parse_listing(self, node: Selector) -> dict[str, Any]:
        """Map a Naef property to the normalised listing fields."""
        # parsel types `.get()` as `str | None`, but `@` on a JSON node yields the dict.
        prop = cast("dict[str, Any]", node.jmespath("@").get())
        return {
            "external_id": prop["no_dossier"],
            "external_url": prop["link"],
            "title": prop["intitule_plaquette"],
            "description": prop["intitule_plaquette"],
            "price_chf": self._price_centimes(prop),
            "nb_rooms": self._to_float(prop.get("nb_pieces")),
            "surface_m2": self._to_float(prop.get("surface_habitable")),
            "city": prop.get("adresse_localite") or None,
            "images": self._images(prop.get("imgs")),
        }

    @staticmethod
    def _price_centimes(prop: dict[str, Any]) -> int | None:
        """Return the gross monthly rent in centimes, None if it is on request.

        The payload can still carry a number when the rent is on request, so the
        flag is checked first: a `0` would slip through the price hard filters.
        """
        if prop.get("loyer_sur_demande") == "oui":
            return None
        rent = prop.get("loyer_mensuel_brut")
        return parse_swiss_price(None if rent in (None, "") else str(rent))

    @staticmethod
    def _to_float(value: str | float | None) -> float | None:
        """Convert a numeric payload value (`"4.5"`, `2`) to float, None if empty."""
        if value is None or value == "":
            return None
        return float(value)

    @staticmethod
    def _images(imgs: list[str] | dict[str, str] | None) -> list[str] | None:
        """Return image URLs, whether `imgs` is a list or an object keyed by index."""
        if isinstance(imgs, dict):
            imgs = list(imgs.values())
        return imgs or None
