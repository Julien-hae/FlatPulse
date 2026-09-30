"""Unit tests for utility functions in the FlatPulse application."""

import os
import unittest

from flatpulse.common.utils import parse_rooms, parse_swiss_price
from flatpulse.config import REQUIRED_VARS, Config


class TestUtils(unittest.TestCase):
    """Unit tests for utility functions."""

    def setUp(self) -> None:
        """Set up test fixtures, if any."""
        self.prices_test_set = {
            "CHF 1'850.–/mois": 185000,  # noqa: RUF001
            "CHF 2'400": 240000,
            "Fr. 950.—": 95000,
            "Prix sur demande": None,
            "Preis auf Anfrage": None,
            None: None,
        }
        self.rooms_test_set = {
            "2 chambres": 2,
            "1.5 pièces": 1.5,
            "Studio": 1.0,
            "3.5 Zimmer": 3.5,
            None: None,
            "2½ pièces": 2.5,
            "4 pièces": 4.0,
        }

    def test_parse_price(self) -> None:
        for test, expected in self.prices_test_set.items():
            self.assertEqual(parse_swiss_price(test), expected)

    def test_parse_rooms(self) -> None:
        for test, expected in self.rooms_test_set.items():
            self.assertEqual(parse_rooms(test), expected)

    def test_config_missing_var_raises(self) -> None:
        """Test that missing required environment variables raise a SystemExit."""

        for var in REQUIRED_VARS:
            if var in os.environ:
                del os.environ[var]

        with self.assertRaises(SystemExit):
            Config()
