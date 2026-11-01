"""Unit tests for the Comptoir Immobilier scraper."""

import unittest

from flatpulse.scrapers.sources.comptoir import ComptoirScraper
from tests.contract.test_scraper_contract import ScraperContractMixin


class TestComptoirScraper(ScraperContractMixin, unittest.IsolatedAsyncioTestCase):
    """Contract tests and named cases of ComptoirScraper.

    `comptoir_cases.html` holds seven cards taken unchanged from the catalogue of
    30.10.2026, without pagination, so a single mocked GET returns every card.
    """

    scraper_class = ComptoirScraper
    fixture_name = "comptoir_cases.html"

    async def test_comptoir_geneva_apartment(self) -> None:
        """A complete Geneva apartment card comes out field by field."""
        await self.assert_listing(
            "bel-appartement-de-25-pices-au-6me-tage-avec-balcon",
            {
                "title": "Bel appartement de 2,5 pièces au 6ème étage avec balcon.",
                "price_chf": 162800,
                "nb_rooms": 2.5,
                "external_id": "bel-appartement-de-25-pices-au-6me-tage-avec-balcon",
            },
        )

    async def test_comptoir_apartment_without_surface(self) -> None:
        """A card without a surface tag keeps its rent and rooms."""
        await self.assert_listing(
            "superbe-appartement-proche-du-centre-ville",
            {
                "title": "Superbe appartement proche du centre-ville",
                "price_chf": 319400,
                "nb_rooms": 4.5,
            },
        )

    async def test_comptoir_vaud_duplex(self) -> None:
        """A Vaud duplex with a long, truncated heading keeps it whole."""
        await self.assert_listing(
            "magnifique-duplex-de-5-5-pices-en-attique-denviron-165m2-dans-un-petit-"
            "immeuble-avec-ascenseur-lavenue-de-lausanne-24-situ-sur-la-commune-dyvorne-"
            "10-minutes-pieds-du-centre-ville-dai",
            {
                # The site's typographic apostrophes, kept as scraped
                "title": "Magnifique duplex de 5.5 pièces en attique d’environ 165m2 "  # noqa: RUF001
                "dans un petit immeuble avec ascenseur, à l’Avenue de Lausanne 24. "  # noqa: RUF001
                "Situé sur la commune d’Yvorne à 10 minutes à pieds du centre ville d’Ai",  # noqa: RUF001
                "price_chf": 307000,
                "nb_rooms": 5.5,
            },
        )

    async def test_comptoir_parking(self) -> None:
        """A parking card has a rent and no rooms."""
        await self.assert_listing(
            "emplacement-de-parking-dans-un-parking-scuris-cet-place-est-louer-"
            "uniquement-des-personnes-extrieures-au-plq-amandolier",
            {"price_chf": 26000, "nb_rooms": None},
        )

    async def test_comptoir_price_on_request_is_none(self) -> None:
        """« Prix sur demande » gives no price, never 0."""
        await self.assert_listing(
            "surface-administrative-dexception-au-coeur-de-genve", {"price_chf": None}
        )

    async def test_comptoir_office_priced_per_m2_per_year(self) -> None:
        """An office priced « / m² / an » is listed under its heading."""
        await self.assert_listing(
            "belles-surfaces-administratives-dans-un-immeuble-de-haut-standing-dans-le-"
            "quartier-des-banques",
            {
                "title": "Belles surfaces administratives dans un immeuble de haut "
                "standing dans le quartier des banques",
                "nb_rooms": None,
            },
        )

    async def test_comptoir_office_priced_per_year(self) -> None:
        """An office priced « / an » is listed under its heading."""
        await self.assert_listing(
            "bureau-louer-au-centre-de-monthey",
            {"title": "Bureau à louer au centre de Monthey", "nb_rooms": None},
        )
