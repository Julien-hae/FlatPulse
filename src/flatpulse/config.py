"""Configuration management for the FlatPulse application."""

import os

REQUIRED_VARS = ["DATABASE_URL", "TELEGRAM_BOT_TOKEN"]


class Config:
    """Represents the application configuration."""

    def __init__(self) -> None:
        """Initialize the configuration by reading environment variables."""
        missing = [v for v in REQUIRED_VARS if not os.environ.get(v)]
        if missing:
            raise SystemExit(
                f"Missing required environment variables: {', '.join(missing)}\n"
                f"Copy .env.example → .env and fill in the values."
            )
        self.database_url = os.environ["DATABASE_URL"]
        self.telegram_token = os.environ["TELEGRAM_BOT_TOKEN"]
        self.log_level = os.environ.get("LOG_LEVEL", "INFO")
        self.log_format = os.environ.get("LOG_FORMAT", "text")
        self.poll_interval = int(os.environ.get("POLL_INTERVAL_DEFAULT", "120"))
