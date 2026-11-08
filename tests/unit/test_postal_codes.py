"""Unit tests for the postal code table and its refresh from swisstopo's open data."""

import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx

from flatpulse.common.postal_codes import (
    COLUMNS,
    TABLE_PATH,
    PostalCode,
    main,
    read_table,
    rows_from_swisstopo,
)
from tests.helpers import FIXTURES_DIR

# Unchanged rows of swisstopo's directory of 01.11.2026: the postal codes of the
# fixtures, 1290 (Versoix GE, Chavannes-des-Bois VD) and 9485 (Liechtenstein).
SWISSTOPO_EXTRACT = FIXTURES_DIR / "swisstopo_localities.csv"


def swisstopo_response() -> MagicMock:
    """The extract zipped as swisstopo serves its directory."""
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr(
            "AMTOVZ_CSV_LV95/AMTOVZ_CSV_LV95.csv", SWISSTOPO_EXTRACT.read_bytes()
        )
    response = MagicMock(content=archive.getvalue())
    response.raise_for_status.return_value = None
    return response


class TestPostalCodes(unittest.TestCase):
    """The table has the columns of the future `postal_codes` SQL table (#133)."""

    def setUp(self) -> None:
        """A table path in a temporary directory, never the committed table."""
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.table = Path(directory.name) / "postal_codes.csv"

    def test_rows_take_the_canton_holding_most_addresses(self) -> None:
        """Versoix is GE although 0.2 % of its addresses lie in Mies (VD)."""
        rows = rows_from_swisstopo(SWISSTOPO_EXTRACT.read_text(encoding="utf-8-sig"))

        self.assertIn(PostalCode("1290", "Versoix", "GE"), rows)
        self.assertIn(PostalCode("1290", "Chavannes-des-Bois", "VD"), rows)
        keys = [(row.postal_code, row.locality) for row in rows]
        self.assertEqual(len(keys), len(set(keys)))

    def test_rows_without_canton_are_left_out(self) -> None:
        """Liechtenstein's localities have no canton: they are not in the table."""
        rows = rows_from_swisstopo(SWISSTOPO_EXTRACT.read_text(encoding="utf-8-sig"))

        self.assertNotIn("9485", {row.postal_code for row in rows})

    def test_refresh_writes_the_table_with_the_sql_columns(self) -> None:
        """The refresh downloads swisstopo once and writes postal_code,locality,canton."""
        with patch(
            "flatpulse.common.postal_codes.httpx.get",
            return_value=swisstopo_response(),
        ) as get:
            main(self.table)

        get.assert_called_once()
        self.assertIn(
            "ch.swisstopo-vd.ortschaftenverzeichnis_plz", get.call_args.args[0]
        )
        header = self.table.read_text(encoding="utf-8").splitlines()[0]
        self.assertEqual(header, ",".join(COLUMNS))
        self.assertEqual(
            read_table(self.table)["1290"],
            {"versoix": "GE", "chavannes-des-bois": "VD"},
        )

    def test_refresh_keeps_the_table_when_swisstopo_is_down(self) -> None:
        """swisstopo unreachable: an explicit error, and the table is left as it was."""
        self.table.write_text("postal_code,locality,canton\n1206,Genève,GE\n")
        before = self.table.read_text(encoding="utf-8")

        with (
            patch(
                "flatpulse.common.postal_codes.httpx.get",
                side_effect=httpx.ConnectError("Network is unreachable"),
            ),
            self.assertRaises(httpx.ConnectError),
        ):
            main(self.table)

        self.assertEqual(self.table.read_text(encoding="utf-8"), before)

    def test_committed_table_has_the_sql_columns(self) -> None:
        """`sql/postal_codes.csv` loads as is with COPY … CSV HEADER (#133)."""
        header = TABLE_PATH.read_text(encoding="utf-8").splitlines()[0]

        self.assertEqual(header, ",".join(COLUMNS))
        self.assertEqual(read_table()["1290"]["versoix"], "GE")
