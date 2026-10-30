"""Unit tests for the Burger Immobilier scraper."""

import unittest
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from flatpulse.scrapers.base import REQUIRED_FIELDS
from flatpulse.scrapers.sources.burger import BurgerScraper
from tests.contract.test_scraper_contract import ScraperContractMixin
from tests.helpers import response_from_fixture

LOUER = "https://www.burger-sa.ch/fr/louer/"


def fake_get(url: str) -> MagicMock:
    """Serve the frozen sitemap, and the frozen fiche of each of its entries."""
    if url == BurgerScraper.base_url:
        return response_from_fixture("burger_sitemap.xml")
    return response_from_fixture(f"burger/{url.removeprefix(LOUER)}.html")


class TestBurgerScraper(ScraperContractMixin, unittest.IsolatedAsyncioTestCase):
    """Contract tests and required fields of BurgerScraper on the frozen fixtures."""

    scraper_class = BurgerScraper
    fixture_name = "burger_sitemap.xml"

    async def fetch_from_fixture(self) -> list[dict[str, Any]]:
        """Serve the sitemap, then its rental fiches."""
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = fake_get
            return await self.scraper_class().fetch_listings()

    async def test_required_fields_are_present(self) -> None:
        """Every listing has every required field filled."""
        for listing in await self.fetch_from_fixture():
            url = listing.get("external_url")
            for field in REQUIRED_FIELDS:
                with self.subTest(url=url, field=field):
                    self.assertTrue(
                        listing.get(field),
                        f"Champ requis '{field}' manquant ou vide pour {url}",
                    )
