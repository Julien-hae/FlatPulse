"""Unit tests for utility functions in the FlatPulse application."""

import os
import unittest
from typing import Any
from unittest.mock import patch

from flatpulse.common.utils import parse_monthly_rent, parse_rooms
from flatpulse.config import REQUIRED_VARS, Config


class TestUtils(unittest.TestCase):
    """Unit tests for utility functions."""

    def setUp(self) -> None:
        """Set up test fixtures, if any."""
        self.prices_test_set: list[dict[str, Any]] = [
            {"input": "CHF 1'850.–/mois", "expected": 185000, "surface_m2": None},  # noqa: RUF001
            {"input": "CHF 2'400", "expected": 240000, "surface_m2": None},
            {"input": "CHF 1'234.56", "expected": 123456, "surface_m2": None},
            {"input": "Fr. 950.—", "expected": 95000, "surface_m2": None},
            {"input": "Prix sur demande", "expected": None, "surface_m2": None},
            {"input": "Prix sur demande", "expected": None, "surface_m2": 10},
            {"input": "Preis auf Anfrage", "expected": None, "surface_m2": None},
            {"input": None, "expected": None, "surface_m2": None},
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
        for test_case in self.prices_test_set:
            self.assertEqual(
                parse_monthly_rent(test_case["input"], test_case["surface_m2"]),
                test_case["expected"],
                test_case["input"],
            )

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
