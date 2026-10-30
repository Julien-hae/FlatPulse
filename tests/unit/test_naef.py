"""Unit tests for the Naef Immobilier scraper."""

import json
import unittest

from flatpulse.scrapers.base import REQUIRED_FIELDS
from flatpulse.scrapers.sources.naef import NaefScraper
from tests.contract.test_scraper_contract import ScraperContractMixin
from tests.helpers import FIXTURES_DIR


class TestNaefScraper(ScraperContractMixin, unittest.IsolatedAsyncioTestCase):
    """Contract tests and required fields of NaefScraper on the frozen fixture."""

    scraper_class = NaefScraper
    fixture_name = "naef_location.json"

    async def test_required_fields_are_present(self) -> None:
        """Every listing has every required field filled."""
        payload = json.loads(
            (FIXTURES_DIR / self.fixture_name).read_text(encoding="utf-8")
        )
        source_listings = {item["no_dossier"]: item for item in payload["props"]}

        for listing in await self.fetch_from_fixture():
            url = listing.get("external_url")
            for field in REQUIRED_FIELDS:
                with self.subTest(url=url, field=field):
                    self.assertTrue(
                        listing.get(field),
                        f"Champ requis '{field}' manquant ou vide. "
                        "JSON source problématique :\n"
                        f"{json.dumps(source_listings[listing['external_id']], ensure_ascii=False, indent=2)}",
                    )

    async def test_title_falls_back_to_type_designation(self) -> None:
        """A missing brochure title is replaced by the property's designation."""
        listing = next(
            item
            for item in await self.fetch_from_fixture()
            if item["external_id"] == "212528.62211"
        )

        self.assertEqual(listing["title"], "Garage individuel")
