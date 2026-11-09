"""Unit tests for utility functions in the FlatPulse application."""

import unittest
from typing import Any

from flatpulse.common.models import PropertyType
from flatpulse.common.utils import (
    canton_code,
    is_monthly_rent,
    parse_floor,
    parse_monthly_rent,
    parse_property_type,
    parse_rooms,
    parse_surface,
    parse_swiss_price,
)


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
            {"input": "Loyer sur demande", "expected": None, "surface_m2": None},
            {"input": "1500/ mois", "expected": 150000, "surface_m2": None},
            {"input": "Dès 1500 + charges", "expected": 150000, "surface_m2": None},
            {"input": "CHF 260.— / m2 / année", "expected": 463667, "surface_m2": 214},
            {"input": "CHF 0.- / mois", "expected": None, "surface_m2": None},
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

    def test_parse_rooms(self) -> None:
        for test, expected in self.rooms_test_set.items():
            self.assertEqual(parse_rooms(test), expected, test)

    def test_parse_surface_bare_number(self) -> None:
        self.assertEqual(parse_surface("119"), 119.0)
        self.assertEqual(parse_surface("118.5"), 118.5)
        self.assertEqual(parse_surface("59 m2"), 59.0)

    def test_parse_surface_rejects_non_decimal_bare_numbers(self) -> None:
        for text in (
            "nan",
            "NaN",
            "inf",
            "-inf",
            "Infinity",
            "1e3",
            "1E+3",
            "1_000",
            "+119",
            "-119",
            ".5",
            "119.",
        ):
            with self.subTest(text=text):
                self.assertIsNone(parse_surface(text))

    def test_parse_surface_preserves_supported_formats(self) -> None:
        cases = {
            " 119 ": 119.0,
            "\t118.5\n": 118.5,
            "59 m²": 59.0,
            "ENV. 60 M2": 60.0,
            "de 85 M2 à 100 M2": 85.0,
            "59 sqm": 59.0,
            "59 square meters": 59.0,
            "": None,
            "sur demande": None,
            None: None,
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_surface(text), expected)

    def test_canton_code(self) -> None:
        self.assertEqual(canton_code("Genève"), "GE")
        self.assertEqual(canton_code("Neuchâtel"), "NE")
        self.assertIsNone(canton_code(""))
        self.assertIsNone(canton_code(None))
        with self.assertLogs("flatpulse.common.utils", "WARNING") as logs:
            self.assertIsNone(canton_code("Atlantide"))
        self.assertIn("Atlantide", logs.output[0])

    def test_parse_floor(self) -> None:
        """Numbered floors, ground floor as 0, basements below 0, None without one."""
        cases = {
            "au 2ème étage": 2,
            "au 1er étage": 1,
            "au 12ème étage": 12,
            "au rez-de-chaussée": 0,
            "au rez-supérieur": 0,
            "au 1er sous-sol": -1,
            "Bel appartement de 5 pièces": None,
            "Studio au 3ème étage, cave au 1er sous-sol": 3,
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_floor(text), expected)

    def test_parse_floor_bare_value(self) -> None:
        """A floor given alone, as in a details table: « 7ème », « 1er », « -1 »."""
        cases = {"7ème": 7, "1er": 1, "-1": -1, "Rez-de-chaussée": 0, "Oui": None}
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_floor(text), expected)

    def test_parse_property_type(self) -> None:
        """The leading label gives the PropertyType; an unknown label gives None."""
        cases = {
            "Appartement 3.0 pièces": PropertyType.APARTMENT,
            "Garage individuel": PropertyType.PARKING,
            "Place couverte": PropertyType.PARKING,
            "Dépôt": PropertyType.STORAGE,
            "Parking": PropertyType.PARKING,
            "Atelier": PropertyType.COMMERCIAL,
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_property_type(text), expected)

    def test_unknown_property_type_is_logged(self) -> None:
        """An unknown label gives None and a WARNING: the agency changed its labels."""
        with self.assertLogs("flatpulse.common.utils", "WARNING") as logs:
            self.assertIsNone(parse_property_type("Château"))
        self.assertIn("Château", logs.output[0])

    def test_is_monthly_rent(self) -> None:
        """Only a rent without a yearly or per-m² unit is monthly."""
        cases = {
            "CHF 2'330.— / mois": True,
            "Dès CHF 2'320.- + charges": True,
            "CHF 24'000.— / année": False,
            "CHF 260.— / m2 / année": False,
            "CHF 25.- / m² / mois": False,
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(is_monthly_rent(text), expected)
