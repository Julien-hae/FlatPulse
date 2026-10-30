"""Unit tests for the Comptoir Immobilier scraper."""

import unittest
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call, patch

from parsel import Selector

from flatpulse.scrapers.base import REQUIRED_FIELDS
from flatpulse.scrapers.sources.comptoir import ComptoirScraper
from tests.contract.test_scraper_contract import ScraperContractMixin
from tests.helpers import response_from_fixture

PAGINATION = """
<ul>
  <li class="mx-3"><a href="https://comptoir-immo.ch/location/?page=2" class="page-number page-numbers text-theme-title">            2
          </a></li>
  <li class="mx-3"><a href="https://comptoir-immo.ch/location/?page=3" class="page-number page-numbers text-theme-title">            3
          </a></li>
  <li class="mx-3"><a href="https://comptoir-immo.ch/location/?page=2" class="next page-numbers">Suivant</a></li>
</ul>"""


def card(slug: str) -> str:
    """Build a minimal property card linking to the given fiche slug."""
    return f"""
<article class="teaser teaser--property_for_rent">
  <a href="https://comptoir-immo.ch/location/appartement/canton-de-geneve/carouge/{slug}/">
    <div class="heading-4">CHF 1'850.- / mois</div>
    <h2><div>Appartement de 3 pièces à Carouge</div></h2>
    <div class="inline-block">Appartement</div>
    <div class="inline-block">3 pièces</div>
  </a>
</article>"""


class TestComptoirScraper(ScraperContractMixin, unittest.IsolatedAsyncioTestCase):
    """Contract and unit tests for ComptoirScraper.

    The fixture holds the whole catalogue (376 cards, pages 1 to 16 of 30.10.2026)
    without its pagination, so a single mocked GET returns every card.
    """

    scraper_class = ComptoirScraper
    fixture_name = "comptoir_listing.html"

    async def listing(self, external_id: str) -> dict[str, Any]:
        """Return the fixture listing whose external_id matches."""
        listings = await self.fetch_from_fixture()
        return next(item for item in listings if item["external_id"] == external_id)

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    async def test_parse_comptoir_fixture(self, mock_get: AsyncMock) -> None:
        """fetch_listings turns every card of the fixture into a listing."""
        mock_get.return_value = response_from_fixture(self.fixture_name)

        result = await ComptoirScraper().fetch_listings()

        self.assertEqual(len(result), 376)
        for item in result:
            self.assertIsInstance(item, dict)
            for field in REQUIRED_FIELDS:
                self.assertIn(field, item)
                self.assertTrue(item[field])
            self.assertIsInstance(item["price_chf"], (int, type(None)))
            self.assertIsInstance(item["nb_rooms"], (float, type(None)))
            self.assertIsInstance(item["surface_m2"], (float, type(None)))

    async def test_every_card_has_a_distinct_id(self) -> None:
        """No two cards of the catalogue share an external_id."""
        listings = await self.fetch_from_fixture()

        ids = [item["external_id"] for item in listings]
        self.assertEqual(len(set(ids)), len(ids))

    async def test_apartment_card(self) -> None:
        """Every field shown on an apartment card is extracted."""
        item = await self.listing("appartement-cologny-situ-dans-un-parc")

        self.assertEqual(item["title"], "Appartement à Cologny situé dans un parc")
        self.assertEqual(
            item["external_url"],
            "https://comptoir-immo.ch/location/appartement/canton-de-geneve/cologny/"
            "appartement-cologny-situ-dans-un-parc/",
        )
        self.assertEqual(item["price_chf"], 750000)
        self.assertEqual(item["nb_rooms"], 5.5)
        self.assertEqual(item["surface_m2"], 160.0)
        self.assertEqual(item["city"], "Cologny")

    async def test_rooms_come_from_the_pieces_tag(self) -> None:
        """'1 pièce', '1.5 pièce' and '5.5 pièces' are read; '3 chambres' is not."""
        studio = await self.listing(
            "studio-de-42m2-louer-au-coeur-de-cour-de-gare-sion"
        )
        one_and_a_half = await self.listing(
            "studio-situ-au-2me-tage-dun-immeuble-avec-ascenseur-proche-de-toutes"
            "-les-commodits-et-espaces-verts"
        )
        cologny = await self.listing("appartement-cologny-situ-dans-un-parc")

        self.assertEqual(studio["nb_rooms"], 1.0)
        self.assertEqual(one_and_a_half["nb_rooms"], 1.5)
        self.assertEqual(cologny["nb_rooms"], 5.5)

    async def test_surface_comes_from_its_own_tag(self) -> None:
        """The m2 tag is read wherever it sits; no m2 tag means None."""
        studio = await self.listing(
            "studio-de-42m2-louer-au-coeur-de-cour-de-gare-sion"
        )
        hall = await self.listing("a-louer-halle-commerciale-conthey")
        no_surface = await self.listing(
            "studio-situ-au-2me-tage-dun-immeuble-avec-ascenseur-proche-de-toutes"
            "-les-commodits-et-espaces-verts"
        )

        self.assertEqual(studio["surface_m2"], 42.0)
        self.assertEqual(hall["surface_m2"], 1182.0)
        self.assertIsNone(no_surface["surface_m2"])

    async def test_price_on_request_is_none(self) -> None:
        """'Prix sur demande' gives None, never 0."""
        item = await self.listing("a-louer-halle-commerciale-conthey")

        self.assertIsNone(item["price_chf"])

    async def test_zero_price_is_none(self) -> None:
        """'CHF 0.- / mois' is no price at all, so it must not pass price filters."""
        item = await self.listing("279533")

        self.assertIsNone(item["price_chf"])

    async def test_yearly_price_per_m2_is_not_a_monthly_rent(self) -> None:
        """'CHF 114.- / m² / an' is not stored as a CHF 114 monthly rent."""
        item = await self.listing(
            "dpot-en-sous-sol-compos-de-2-locaux-dune-surface-totale-denviron-90-m%c2%b2"
        )

        self.assertIsNone(item["price_chf"])

    async def test_card_without_title_still_has_a_title(self) -> None:
        """Some parking cards have an empty <h2>; the listing still gets a title."""
        item = await self.listing("279533")

        self.assertTrue(item["title"])

    def test_nb_pages_reads_the_last_page_number(self) -> None:
        """The highest numbered link wins; 'Suivant' and whitespace are ignored."""
        self.assertEqual(ComptoirScraper.nb_pages(Selector(text=PAGINATION)), 3)

    def test_nb_pages_without_pagination_is_one(self) -> None:
        """A catalogue that fits on one page has no pagination links."""
        self.assertEqual(ComptoirScraper.nb_pages(Selector(text=card("seul"))), 1)

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    async def test_fetch_listings_reads_every_page(self, mock_get: AsyncMock) -> None:
        """Each page announced by page 1 is requested once and its cards kept."""
        mock_get.side_effect = [
            MagicMock(text=card("premier") + PAGINATION),
            MagicMock(text=card("deuxieme") + PAGINATION),
            MagicMock(text=card("troisieme") + PAGINATION),
        ]

        result = await ComptoirScraper().fetch_listings()

        self.assertEqual(
            mock_get.await_args_list,
            [call(f"https://comptoir-immo.ch/location/?page={n}") for n in (1, 2, 3)],
        )
        self.assertEqual(
            [item["external_id"] for item in result],
            ["premier", "deuxieme", "troisieme"],
        )
