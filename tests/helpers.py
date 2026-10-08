"""Helpers shared by test modules."""

from pathlib import Path
from unittest.mock import MagicMock

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def response_from_fixture(filename: str) -> MagicMock:
    """Build a fake httpx response whose body is the given fixture file."""
    response = MagicMock()
    response.text = (FIXTURES_DIR / filename).read_text(encoding="utf-8")
    response.raise_for_status.return_value = None
    return response
