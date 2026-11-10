"""Unit tests for postal codes in memory: swisstopo parsing, canton lookup, completion."""

import unittest
from unittest.mock import Mock

from flatpulse.common.models import Listing
from flatpulse.common.postal_codes import (
    CantonLookup,
    PostalCode,
    fill_missing_canton,
    rows_from_swisstopo,
)
from tests.helpers import SWISSTOPO_EXTRACT


def extract_rows() -> list[PostalCode]:
    """The table rows of the swisstopo extract."""
    return rows_from_swisstopo(SWISSTOPO_EXTRACT.read_text(encoding="utf-8-sig"))


class TestRowsFromSwisstopo(unittest.TestCase):
    """The rows have the columns of the `postal_codes` SQL table (`sql/schema.sql`)."""

    def test_rows_take_the_canton_holding_most_addresses(self) -> None:
        """Versoix is GE although 0.2 % of its addresses lie in Mies (VD)."""
        rows = extract_rows()

        self.assertIn(PostalCode("1290", "Versoix", "GE"), rows)
        self.assertIn(PostalCode("1290", "Chavannes-des-Bois", "VD"), rows)
        keys = [(row.postal_code, row.locality) for row in rows]
        self.assertEqual(len(keys), len(set(keys)))

    def test_rows_without_canton_are_left_out(self) -> None:
        """Liechtenstein's localities have no canton: they are not in the table."""
        self.assertNotIn("9485", {row.postal_code for row in extract_rows()})


class TestCantonLookup(unittest.TestCase):
    def setUp(self) -> None:
        self.lookup = CantonLookup(extract_rows())

    def test_single_canton_postal_code(self) -> None:
        """A postal code within one canton gives that canton, whatever the town."""
        self.assertEqual(self.lookup.canton("1206", None), "GE")
        self.assertEqual(self.lookup.canton("1070", "Puidoux"), "VD")
        self.assertEqual(self.lookup.canton("2300", "Chaux-de-Fonds"), "NE")

    def test_shared_postal_code_uses_locality(self) -> None:
        """1290 is Versoix (GE) and Chavannes-des-Bois (VD): the locality decides."""
        self.assertEqual(self.lookup.canton("1290", "Versoix"), "GE")
        self.assertEqual(self.lookup.canton("1290", "Chavannes-des-Bois"), "VD")
        self.assertEqual(self.lookup.canton("1290", "versoix"), "GE")

    def test_ambiguous_or_unknown_is_none(self) -> None:
        """No canton is guessed: a shared code without its town, or an unknown one."""
        self.assertIsNone(self.lookup.canton(None, None))
        cases = (("1290", None), ("1290", "Nyon"), ("0000", None), ("9485", "Nendeln"))
        for postal_code, locality in cases:
            with (
                self.subTest(postal_code=postal_code, locality=locality),
                self.assertLogs("flatpulse.common.postal_codes", "WARNING") as logs,
            ):
                self.assertIsNone(self.lookup.canton(postal_code, locality))
            self.assertIn(postal_code, logs.output[0])


class TestFillMissingCanton(unittest.TestCase):
    def test_pipeline_fills_missing_canton_from_postal_code(self) -> None:
        """The canton written by the source wins; the postal code only fills a gap."""
        lookup = Mock(spec=CantonLookup)
        lookup.canton.return_value = "VD"
        naef = Listing(
            external_id="214177.1113",
            external_url="https://www.naef.ch/louer/appartements/puidoux/214177.1113",
            title="Appartement de 3½ pièces",
            postal_code="1070",
            city="Puidoux",
        )
        comptoir = Listing(
            external_id="901969",
            external_url="https://www.comptoir-immo.ch/location/901969",
            title="Bureau à louer au centre de Sion",
            city="Sion",
            canton="VS",
        )

        self.assertEqual(fill_missing_canton(naef, lookup).canton, "VD")
        self.assertEqual(fill_missing_canton(comptoir, lookup).canton, "VS")
        lookup.canton.assert_called_once_with("1070", "Puidoux")
