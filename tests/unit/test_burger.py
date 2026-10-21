"""Unit tests for the Burger Immobilier scraper."""

import unittest
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from flatpulse.scrapers.sources.burger import BurgerScraper
from tests.contract.test_scraper_contract import ScraperContractMixin

URL = "https://www.burger-sa.ch/fr/louer/geneve-appartement-de-charme"
SITEMAP = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://www.burger-sa.ch/fr/acheter/duplex-a-bernex</loc></url>
<url><loc>{URL}</loc></url>
</urlset>"""
FICHE = f"""<html><head><link href="{URL}" rel="canonical" /></head><body>
<h1>Appartement de charme</h1>
<div class="swiper-slide"><img data-src="corumfiles/images/001.JPG" /></div>
<div class="prose">Au coeur de la Vieille-Ville.</div>
<div class="flex"><div>Loyer</div><div>CHF 7'000.— / mois</div></div>
<div class="space-y-4 mt-6">
  <div class="text-base">Place du Bourg-de-Four 9<br>1204 Genève</div>
  <div class="text-sm">Appartement 0.0 pièces</div>
  <div class="text-sm">180 m2</div>
</div>
</body></html>"""


class TestBurgerScraper(ScraperContractMixin, unittest.IsolatedAsyncioTestCase):
    """Contract and unit tests for BurgerScraper."""

    scraper_class = BurgerScraper

    async def fetch_from_fixture(self) -> list[dict[str, Any]]:
        """Serve the sitemap and its rental fiche."""
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = lambda url: MagicMock(
                text=SITEMAP if url.endswith("sitemap.php") else FICHE
            )
            return await self.scraper_class().fetch_listings()

    async def test_parses_each_rental_fiche_of_the_sitemap(self) -> None:
        """Only /fr/louer/ fiches are parsed; "0.0 pièces" means an unknown count."""
        [listing] = await self.fetch_from_fixture()

        self.assertEqual(listing["external_id"], URL)
        self.assertEqual(listing["title"], "Appartement de charme")
        self.assertEqual(listing["price_chf"], 700000)
        self.assertIsNone(listing["nb_rooms"])
        self.assertEqual(listing["surface_m2"], 180.0)
        self.assertEqual(listing["address"], "Place du Bourg-de-Four 9")
        self.assertEqual(listing["city"], "Genève")
        self.assertEqual(listing["description"], "Au coeur de la Vieille-Ville.")
        self.assertEqual(
            listing["images"], ["https://www.burger-sa.ch/corumfiles/images/001.JPG"]
        )
