"""Data models for the FlatPulse application."""

import hashlib
import re
from dataclasses import dataclass, fields
from enum import StrEnum
from typing import get_type_hints

from httpx import URL


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

    listing: Listing
    profile_id: int
    user_id: int
    score: float
    matched_criteria: Listing


@dataclass
class ScrapingStats:
    """Represents scraping statistics for the FlatPulse application."""

    new_listings_last_hour: int = 0
    new_listings_last_6h: int = 0
    consecutive_errors: int = 0


class PropertyType(StrEnum):
    """Property types."""

    APARTMENT = "apartment"
    HOUSE = "house"
    PARKING = "parking"
    COMMERCIAL = "commercial"  # bureau, arcade, commerce, atelier
    STORAGE = "storage"  # dépôt


@dataclass(frozen=True, slots=True, kw_only=True)
class Listing:
    """Represents a real estate listing."""

    external_id: str
    external_url: URL
    title: str
    property_type: PropertyType | None = None
    price_chf: int | None = None  # centimes, loyer MENSUEL charges comprises
    charges_chf: int | None = None  # centimes, part des charges dans price_chf
    nb_rooms: float | None = None
    surface_m2: float | None = None
    floor: int | None = None  # 0 = rez, négatif = sous-sol
    address: str | None = None  # rue et numéro
    postal_code: str | None = None
    city: str | None = None
    canton: str | None = None  # code à deux lettres : "GE", "VD"…
    description: str | None = None
    images: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Check fields."""
        if not isinstance(self.external_url, URL):
            object.__setattr__(self, "external_url", URL(self.external_url))
        self._set_empty_str_fields_to_none()
        self._required_fields()
        self._validate_positive_fields()
        self._validate_canton()

    def _validate_canton(self) -> None:
        """Validate canton."""
        if self.canton is not None and re.fullmatch(r"[A-Z]{2}", self.canton) is None:
            raise ValueError("canton must contain exactly two uppercase letters")

    def _required_fields(self) -> None:
        """Validate required fields."""
        if not self.external_id.strip():
            raise ValueError("external_id cannot be empty")
        if not self.title.strip():
            raise ValueError("title cannot be empty")
        if not self.external_url.is_absolute_url:
            raise ValueError(
                f"external_url cannot be empty or relative : {self.external_url}"
            )

    def _validate_positive_fields(self) -> None:
        """Validate positive fields."""
        if self.charges_chf is not None and self.charges_chf < 0:
            raise ValueError(f"charges_chf must be positive : got {self.charges_chf}")
        if self.nb_rooms is not None and self.nb_rooms <= 0:
            raise ValueError(
                f"nb_rooms must be strictly positive : got {self.nb_rooms}"
            )
        if self.price_chf is not None and self.price_chf <= 0:
            raise ValueError(
                f"price_chf must be strictly positive : got {self.price_chf}"
            )

    def _set_empty_str_fields_to_none(self) -> None:
        """Set blank optional string fields to None."""
        hints = get_type_hints(type(self))
        for field in fields(self):
            if hints[field.name] == str | None:
                value = getattr(self, field.name)
                if value is not None and not value.strip():
                    object.__setattr__(self, field.name, None)

    @property
    def fingerprint(self) -> str:
        """Compute a unique fingerprint for a listing based on its URL, title, and ID."""
        fingerprint_source = f"{self.external_url!s}|{self.title}|{self.price_chf}"
        return hashlib.sha256(fingerprint_source.encode()).hexdigest()
