"""Utility functions for the FlatPulse application."""

import re


def parse_swiss_price(text: str | None) -> int | None:
    """Format a Swiss price string into an integer representing the price in centimes."""
    if text is None:
        return None
    cleaned_text = re.sub(r"[^\d]", "", text)
    if not cleaned_text:
        return None
    return int(cleaned_text) * 100


def parse_rooms(text: str | None) -> float | None:
    """Format a Swiss rooms string into a float representing the number of rooms."""
    if text is None:
        return None
    if "Studio" in text:
        return 1.0
    match = re.search(r"(\d+)(?:\.(\d+))?(½)?", text)
    if match:
        rooms = float(match.group(1))
        if match.group(2):
            rooms += float(f"0.{match.group(2)}")
        if match.group(3):
            rooms += 0.5
        return rooms
    return None
