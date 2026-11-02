"""Unit tests for utility functions in the FlatPulse application."""

import os
import unittest
from typing import Any
from unittest.mock import patch

from flatpulse.common.utils import parse_monthly_rent, parse_rooms, parse_swiss_price
from flatpulse.config import REQUIRED_VARS, Config


class TestUtils(unittest.TestCase):
    """Unit tests for utility functions."""

    def setUp(self) -> None:
        """Set up test fixtures, if any."""
        self.prices_test_set = {
            "CHF 1'850.–/mois": 185000,  # noqa: RUF001
            "CHF 2'400": 240000,
            "CHF 1'234.56": 123456,
            "Fr. 950.—": 95000,
            "Prix sur demande": None,
            "Preis auf Anfrage": None,
            None: None,
        }
        self.monthly_prices_test_set: list[dict[str, Any]] = [
            {"input": "CHF 18'720.- / an", "expected": 156000, "surface_m2": None},
            {"input": "CHF 24'000.— / année", "expected": 200000, "surface_m2": None},
            {"input": "CHF 600.- / m² / an", "expected": 585000, "surface_m2": 117},
            {"input": "CHF 260.— / m2 / année", "expected": None, "surface_m2": None},
            {"input": "CHF 260.— / m2 / année", "expected": 463667, "surface_m2": 214},
        ]
        self.rooms_test_set = {
            "2 chambres": 2,
            "1.5 pièces": 1.5,
            "Studio": 1.0,
            "3.5 Zimmer": 3.5,
            None: None,
            "2½ pièces": 2.5,
            "4 pièces": 4.0,
            "9 Rue des Eaux-Vives, 4 pièces": 4.0,
        }

    def test_parse_price(self) -> None:
        for test, expected in self.prices_test_set.items():
            self.assertEqual(parse_swiss_price(test), expected, test)

    def test_parse_monthly_price(self) -> None:
        for test_case in self.monthly_prices_test_set:
            self.assertEqual(
                parse_monthly_rent(test_case["input"], test_case["surface_m2"]),
                test_case["expected"],
                test_case["input"],
            )

    def test_period_word_elsewhere_in_the_line_is_ignored(self) -> None:
        """Only a unit written after the amount counts: a 12x too low rent passes every budget."""
        cases = {
            "CHF 2'000.- / mois, indexation annuelle": 200000,
            "CHF 2'000.- / mois (CHF 24'000.- / an)": 200000,
            "CHF 1'500.- charges annuelles comprises": 150000,
            "CHF 18'720.- par an": 156000,
            "CHF 18'720.- p.a.": 156000,
            "CHF 24'000.- pro Jahr": 200000,
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_monthly_rent(text, None), expected)

    def test_parse_rooms(self) -> None:
        for test, expected in self.rooms_test_set.items():
            self.assertEqual(parse_rooms(test), expected, test)

    def test_config_missing_var_raises(self) -> None:
        """Test that missing required environment variables raise a SystemExit."""
        with patch.dict(os.environ):
            for var in REQUIRED_VARS:
                os.environ.pop(var, None)

            with self.assertRaises(SystemExit):
                Config()
