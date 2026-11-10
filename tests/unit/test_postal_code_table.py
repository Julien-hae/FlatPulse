"""Unit tests for the postal code table: its loading at startup, its refresh command."""

import os
import subprocess
import sys
import unittest
from unittest.mock import AsyncMock, patch

from flatpulse.postal_code_table import load_canton_lookup, main


class TestLoadCantonLookup(unittest.IsolatedAsyncioTestCase):
    async def test_load_reads_the_table_once(self) -> None:
        """The lookup is the table read once, by a SELECT, then kept in memory."""
        rows = [{"postal_code": "1290", "locality": "Versoix", "canton": "GE"}]
        with patch(
            "flatpulse.postal_code_table.db.get_postal_codes",
            AsyncMock(return_value=rows),
        ) as get_postal_codes:
            lookup = await load_canton_lookup()

        get_postal_codes.assert_awaited_once()
        self.assertEqual(lookup.canton("1290", "Versoix"), "GE")

    async def test_load_empty_table_raises(self) -> None:
        """An empty table stops the startup: every canton would be None silently."""
        with (
            patch(
                "flatpulse.postal_code_table.db.get_postal_codes",
                AsyncMock(return_value=[]),
            ),
            self.assertRaises(RuntimeError) as raised,
        ):
            await load_canton_lookup()
        self.assertIn("python -m flatpulse.postal_code_table", str(raised.exception))


class TestRefreshCommand(unittest.TestCase):
    def test_main_without_database_url_exits(self) -> None:
        """The refresh writes to PostgreSQL: no DATABASE_URL, a clear stop."""
        with (
            patch.dict(os.environ, clear=True),
            self.assertRaises(SystemExit) as raised,
        ):
            main()
        self.assertIn("DATABASE_URL", str(raised.exception))


class TestScrapersStayOffTheDatabase(unittest.TestCase):
    def test_importing_a_scraper_does_not_load_the_database_layer(self) -> None:
        """Scrapers only need the lookup in memory, not psycopg nor `flatpulse.db`.

        Checked in a fresh interpreter: this process has already imported `db`.
        """
        script = (
            "import sys\n"
            "import flatpulse.scrapers.sources.naef\n"
            "import flatpulse.scrapers.sources.burger\n"
            "import flatpulse.scrapers.sources.comptoir\n"
            "loaded = sorted({'flatpulse.db', 'psycopg'} & set(sys.modules))\n"
            "sys.exit(', '.join(loaded) or 0)\n"
        )

        # The interpreter and the script are ours: nothing here comes from outside.
        result = subprocess.run(  # noqa: S603
            [sys.executable, "-c", script], capture_output=True, text=True, check=False
        )

        self.assertEqual(result.returncode, 0, f"loaded: {result.stderr.strip()}")
