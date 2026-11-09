"""Unit tests for the in-memory DeduplicationService (#46)."""

import unittest

from flatpulse.common.models import Listing
from flatpulse.scrapers.dedup import DeduplicationService


def listing(external_id: str = "123", price_chf: int | None = 185000) -> Listing:
    """A Plainpalais listing; its price sets its fingerprint."""
    return Listing(
        external_id=external_id,
        external_url=f"https://www.naef.ch/louer/appartements/geneve/{external_id}",
        title="Appartement de 3½ pièces à Plainpalais",
        price_chf=price_chf,
    )


class TestDeduplicationService(unittest.TestCase):
    def setUp(self) -> None:
        self.dedup = DeduplicationService()

    def test_new_listing_is_new(self) -> None:
        """A listing never seen goes through the pipeline."""
        self.assertTrue(self.dedup.is_new(listing(), source_slug="naef"))

    def test_duplicate_not_new(self) -> None:
        """The same listing on the next poll is not notified again."""
        self.assertTrue(self.dedup.is_new(listing(), source_slug="naef"))

        self.assertFalse(self.dedup.is_new(listing(), source_slug="naef"))

    def test_price_change_detected(self) -> None:
        """Same source and id, new price: a new fingerprint, worth notifying again."""
        self.dedup.is_new(listing(price_chf=185000), source_slug="naef")
        cheaper = listing(price_chf=175000)

        self.assertFalse(self.dedup.is_new(cheaper, source_slug="naef"))
        self.assertTrue(self.dedup.has_changed(cheaper, source_slug="naef"))

    def test_different_sources_same_external_id(self) -> None:
        """Two agencies may share an id scheme: the key is source and id."""
        self.dedup.is_new(listing(), source_slug="naef")

        self.assertTrue(self.dedup.is_new(listing(), source_slug="burger"))

    def test_change_is_reported_once(self) -> None:
        """A price change is detected once, not on every following poll."""
        self.dedup.is_new(listing(price_chf=185000), source_slug="naef")
        cheaper = listing(price_chf=175000)

        self.assertTrue(self.dedup.has_changed(cheaper, source_slug="naef"))
        self.assertFalse(self.dedup.has_changed(cheaper, source_slug="naef"))

    def test_unknown_listing_has_not_changed(self) -> None:
        """A listing never seen is new, not changed."""
        self.assertFalse(self.dedup.has_changed(listing(), source_slug="naef"))
