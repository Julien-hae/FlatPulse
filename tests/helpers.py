"""Helpers shared by test modules."""

import io
import zipfile
from pathlib import Path
from unittest.mock import MagicMock

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def response_from_fixture(filename: str) -> MagicMock:
    """Build a fake httpx response whose body is the given fixture file."""
    response = MagicMock()
    response.text = (FIXTURES_DIR / filename).read_text(encoding="utf-8")
    response.raise_for_status.return_value = None
    return response


# Unchanged rows of swisstopo's directory of 01.11.2026: the postal codes of the
# fixtures, 1290 (Versoix GE, Chavannes-des-Bois VD) and 9485 (Liechtenstein).
SWISSTOPO_EXTRACT = FIXTURES_DIR / "swisstopo_localities.csv"


def swisstopo_response() -> MagicMock:
    """A fake httpx response serving the extract zipped, as swisstopo serves it."""
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr(
            "AMTOVZ_CSV_LV95/AMTOVZ_CSV_LV95.csv", SWISSTOPO_EXTRACT.read_bytes()
        )
    response = MagicMock(content=archive.getvalue())
    response.raise_for_status.return_value = None
    return response
