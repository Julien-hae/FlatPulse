"""Configuration management for the FlatPulse application."""

import logging
import os

from flatpulse.common import postal_codes
from flatpulse.common.logging_configuration import log_level_name

REQUIRED_VARS = ["DATABASE_URL", "TELEGRAM_BOT_TOKEN"]


class Config:
    """Represents the application configuration."""

    def __init__(self) -> None:
        """Initialize the configuration by reading environment variables."""
        missing = [v for v in REQUIRED_VARS if not os.environ.get(v)]
        if missing:
            raise SystemExit(
                f"Missing required environment variables: {', '.join(missing)}\n"
                "Export them before starting; nothing reads .env by itself: "
                "`set -a; . ./.env; set +a` loads it into the shell (see .env.example)."
            )
        if not postal_codes.TABLE_PATH.is_file():
            raise SystemExit(
                f"Missing postal code table: {postal_codes.TABLE_PATH}\n"
                "It is read from the repository checkout (sql/postal_codes.csv) "
                "until it moves to PostgreSQL (#133)."
            )
        self.database_url = os.environ["DATABASE_URL"]
        self.telegram_token = os.environ["TELEGRAM_BOT_TOKEN"]
        self.log_level = log_level_name()
        if not isinstance(logging.getLevelName(self.log_level), int):
            raise SystemExit(
                f"LOG_LEVEL must be DEBUG, INFO, WARNING, ERROR or CRITICAL, "
                f"got {self.log_level!r}"
            )
        self.poll_interval_default = _positive_int("POLL_INTERVAL_DEFAULT", 120)


def _positive_int(name: str, default: int) -> int:
    """The positive whole number in variable `name`; unset or empty, `default`.

    Anything else stops the process with the variable named, never a bare ValueError.
    """
    raw = os.environ.get(name) or str(default)
    if not raw.isdecimal() or int(raw) == 0:
        raise SystemExit(f"{name} must be a positive whole number, got {raw!r}")
    return int(raw)
