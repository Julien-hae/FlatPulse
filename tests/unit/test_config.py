"""Unit tests for the configuration read from the environment (#62)."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flatpulse.config import REQUIRED_VARS, Config

# The required variables, set: the only environment a test starts from.
REQUIRED_ENV = dict.fromkeys(REQUIRED_VARS, "set")


class TestConfig(unittest.TestCase):
    """`Config()` reads the environment once, with a fallback for every optional value."""

    def test_config_loads_defaults(self) -> None:
        """Only the required variables set: the app starts with sensible values."""
        with patch.dict(os.environ, REQUIRED_ENV, clear=True):
            config = Config()

        self.assertEqual(config.poll_interval_default, 120)
        self.assertEqual(config.log_level, "INFO")

    def test_config_overrides_from_env(self) -> None:
        """LOG_LEVEL set: the environment drives the configuration (dev vs prod)."""
        with patch.dict(os.environ, {**REQUIRED_ENV, "LOG_LEVEL": "DEBUG"}, clear=True):
            config = Config()

        self.assertEqual(config.log_level, "DEBUG")

    def test_config_missing_var_raises(self) -> None:
        """A required variable missing: the process stops at startup."""
        with patch.dict(os.environ, clear=True), self.assertRaises(SystemExit):
            Config()

    def test_config_missing_postal_code_table_raises(self) -> None:
        """No postal code table: the process stops at startup, not at the first poll.

        Read later, inside parse_listing, a missing file would end a whole poll.
        """
        missing = Path(tempfile.gettempdir()) / "flatpulse-no-such-table.csv"
        with (
            patch.dict(os.environ, REQUIRED_ENV, clear=True),
            patch("flatpulse.config.postal_codes.TABLE_PATH", missing),
            self.assertRaises(SystemExit) as raised,
        ):
            Config()
        self.assertIn(str(missing), str(raised.exception))

    def test_config_reads_the_postal_code_table(self) -> None:
        """With the committed table, the configuration loads."""
        with patch.dict(os.environ, REQUIRED_ENV, clear=True):
            Config()
