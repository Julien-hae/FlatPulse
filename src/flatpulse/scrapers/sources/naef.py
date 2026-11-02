"""Scraper for Naef Immobilier, which exposes its whole catalogue as one JSON payload."""

from parsel import Selector

from flatpulse.common.models import Listing
from flatpulse.common.utils import parse_monthly_rent, parse_rooms, parse_surface
from flatpulse.scrapers.base import HttpScraper


class NaefScraper(HttpScraper):
    """Scrape rental listings from the Naef `get_all_props` endpoint."""

    base_url = (
        "https://www.naef.ch/wp-admin/admin-ajax.php?action=get_all_props&type=Location"
    )

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
        surface_m2 = parse_surface(self._text(node, "surface_habitable"))
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
            images=tuple(node.jmespath("imgs[*]").getall()),
        )

    @staticmethod
    def _text(node: Selector, key: str) -> str | None:
        """Return the value at `key` as a string, or None when absent or empty."""
        value = node.jmespath(key).get()
        return str(value) if value not in (None, "") else None
