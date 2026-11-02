"""Utility functions for the FlatPulse application."""

import re


def parse_swiss_price(text: str | None) -> int | None:
    """Format a Swiss price string into an integer representing the price in centimes."""
    if text is None:
        return None
    match = re.search(
        r"(?P<francs>\d(?:[\d'\u2019\s]*\d)?)(?:\.(?P<cents>\d{1,2}))?",
        text,
    )
    if match is None:
        return None
    francs = int(re.sub(r"[^\d]", "", match.group("francs")))
    cents_text = match.group("cents")
    cents = int(cents_text.ljust(2, "0")) if cents_text else 0
    return francs * 100 + cents


_PER_YEAR = re.compile(
    r"/\s*(an|année)\b|par an|annuel|p\.\s?a\.|pro jahr|/\s*jahr|jährlich", re.I
)
_PER_M2 = re.compile(r"/\s*m[²2]\b|par m[²2]|pro m[²2]", re.I)


def parse_swiss_rent(text: str | None, surface_m2: float | None = None) -> int | None:
    """Monthly rent in centimes, whatever the period or unit the agency displays.

    « / an » is divided by 12; « / m² » is multiplied by the surface,
    and gives None without a surface rather than a per-m² amount posing as a rent.
    """
    amount = parse_swiss_price(text)
    if amount is None or text is None:
        return None
    if _PER_M2.search(text):
        if surface_m2 is None:
            return None
        amount = round(amount * surface_m2)
    if _PER_YEAR.search(text):
        amount = round(amount / 12)
    return amount


def parse_rooms(text: str | None) -> float | None:
    """Format a Swiss rooms string into a float representing the number of rooms."""
    if text is None:
        return None
    if "studio" in text.lower():
        return 1.0
    bare = re.fullmatch(r"\s*(\d+(?:\.\d+)?)(½)?\s*", text)
    if bare:
        return float(bare.group(1)) + (0.5 if bare.group(2) else 0.0)
    match = re.search(
        r"(\d+)(?:\.(\d+))?(½)?\s*(?:pièces?|chambres?|zimmer)\b",
        text,
        re.IGNORECASE,
    )
    if match:
        rooms = float(match.group(1))
        if match.group(2):
            rooms += float(f"0.{match.group(2)}")
        if match.group(3):
            rooms += 0.5
        return rooms
    return None


def parse_surface(text: str | None) -> float | None:
    """Format a Swiss surface string into a float representing the surface in square meters."""
    if text is None:
        return None
    match = re.search(
        r"(\d+(?:\.\d+)?)\s*(?:m²|m2|sqm|square meters?)",
        text,
        re.IGNORECASE,
    )
    if match:
        return float(match.group(1))
    return None
