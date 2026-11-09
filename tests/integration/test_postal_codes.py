"""Tests of the postal code table refresh (#133) against a real PostgreSQL.

Same disposable database as tests/integration/test_db.py, given in
FLATPULSE_TEST_DATABASE_URL (provided by the CI); without it they are skipped.
"""

import os
import unittest
from unittest.mock import patch

import httpx
import psycopg

from flatpulse import db
from flatpulse.common.postal_codes import CantonLookup, PostalCode, refresh
from tests.helpers import swisstopo_response
from tests.unit.test_postal_codes import extract_rows

TEST_DATABASE_URL = os.environ.get("FLATPULSE_TEST_DATABASE_URL", "")

# The table as an earlier refresh left it: one row swisstopo no longer lists.
LOADED = [
    PostalCode("1206", "Genève", "GE"),
    PostalCode("1999", "Localité disparue", "VD"),
]


@unittest.skipUnless(
    TEST_DATABASE_URL, "Set FLATPULSE_TEST_DATABASE_URL to a disposable database"
)
class TestPostalCodesRefresh(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        await db.open_pool(TEST_DATABASE_URL)
        self.addAsyncCleanup(db.close_pool)
        await db.replace_postal_codes(LOADED)

    async def table(self) -> set[PostalCode]:
        return {PostalCode(**row) for row in await db.get_postal_codes()}

    async def test_postal_codes_refresh_replaces_the_table(self) -> None:
        """The refresh is the only write: the table becomes exactly swisstopo's rows."""
        with patch(
            "flatpulse.common.postal_codes.httpx.get",
            return_value=swisstopo_response(),
        ):
            count = await refresh()

        self.assertEqual(await self.table(), set(extract_rows()))
        self.assertEqual(count, len(extract_rows()))
        lookup = await CantonLookup.load()
        self.assertEqual(lookup.canton("1290", "Versoix"), "GE")

    async def test_postal_codes_refresh_keeps_the_table_when_swisstopo_is_down(
        self,
    ) -> None:
        """A swisstopo outage never empties the table."""
        with (
            patch(
                "flatpulse.common.postal_codes.httpx.get",
                side_effect=httpx.ConnectError("Network is unreachable"),
            ),
            self.assertRaises(httpx.ConnectError),
        ):
            await refresh()

        self.assertEqual(await self.table(), set(LOADED))

    async def test_postal_codes_replace_is_one_transaction(self) -> None:
        """A row refused halfway through rolls the TRUNCATE back with it."""
        rows = [PostalCode("1290", "Versoix", "GE"), PostalCode("1290", "Mies", "vd")]

        with self.assertRaises(psycopg.errors.CheckViolation):
            await db.replace_postal_codes(rows)

        self.assertEqual(await self.table(), set(LOADED))
