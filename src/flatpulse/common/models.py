"""Data models for the FlatPulse application."""

from dataclasses import dataclass
from typing import Any


@dataclass
class SourceConfig:
    """Represents the configuration for a data source."""

    slug: str
    name: str
    base_url: str
    scraper_class: str
    poll_interval_s: int = 120
    rate_limit_rpm: int = 10


@dataclass
class MatchResult:
    """Represents the result of a matching operation."""

    listing: dict[str, Any]
    profile_id: int
    user_id: int
    score: float
    matched_criteria: dict[str, Any]


@dataclass
class ScrapingStats:
    """Represents scraping statistics for the FlatPulse application."""

    new_listings_last_hour: int = 0
    new_listings_last_6h: int = 0
    consecutive_errors: int = 0
