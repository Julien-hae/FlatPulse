"""Utility functions for the FlatPulse application."""

import logging
import re

from flatpulse.common.models import PropertyType

logger = logging.getLogger(__name__)

# A period or unit counts only when written as one, right after a slash or « par » /
# « pro » (« / an », « par année », « / m² / an », « pro Jahr ») or as « p.a. »: a word
# elsewhere in the line (« indexation annuelle ») must not divide a monthly rent by 12.
_UNIT = r"(?:/|\bpar\b|\bpro\b)\s*"
_PER_MONTH = re.compile(_UNIT + r"(?:mois|monat)\b", re.I)
_PER_YEAR = re.compile(_UNIT + r"(?:an|année|jahr)\b|\bp\.\s?a\.", re.I)
_PER_M2 = re.compile(_UNIT + r"m[²2]\b", re.I)
# Francs with an apostrophe or a space between thousands, then optional centimes.
_PRICE = re.compile(r"(?P<francs>\d(?:[\d'\u2019\s]*\d)?)(?:\.(?P<cents>\d{1,2}))?")
_ORDINAL = r"(?:er|e|ème|eme)?"
_FLOOR = re.compile(
    rf"\b(?:(?P<ground>rdc|rez)|(?P<basement>\d+){_ORDINAL} sous-sol"
    rf"|(?P<floor>\d+){_ORDINAL} [ée]tage)\b",
    re.IGNORECASE,
)
_BARE_FLOOR = re.compile(rf"\s*(-?\d+){_ORDINAL}\s*", re.IGNORECASE)
_PROPERTY_TYPES = {
    "appartement": PropertyType.APARTMENT,
    "studio": PropertyType.APARTMENT,
    "maison": PropertyType.HOUSE,
    "place ouverte": PropertyType.PARKING,
    "place couverte": PropertyType.PARKING,
    "garage individuel": PropertyType.PARKING,
    "parking": PropertyType.PARKING,
    "atelier": PropertyType.COMMERCIAL,
    "arcade": PropertyType.COMMERCIAL,
    "bureau": PropertyType.COMMERCIAL,
    "commerce": PropertyType.COMMERCIAL,
    "dépôt": PropertyType.STORAGE,
}
_PROPERTY_TYPE = re.compile(rf"\s*({'|'.join(_PROPERTY_TYPES)})\b", re.IGNORECASE)
CANTON_TO_ABR = {
    "Zurich": "ZH",
    "Berne": "BE",
    "Lucerne": "LU",
    "Uri": "UR",
    "Schwytz": "SZ",
    "Obwald": "OW",
    "Nidwald": "NW",
    "Glaris": "GL",
    "Zoug": "ZG",
    "Fribourg": "FR",
    "Soleure": "SO",
    "Bâle-Ville": "BS",
    "Bâle-Campagne": "BL",
    "Schaffhouse": "SH",
    "Appenzell Rhodes-Extérieures": "AR",
    "Appenzell Rhodes-Intérieures": "AI",
    "Saint-Gall": "SG",
    "Grisons": "GR",
    "Argovie": "AG",
    "Thurgovie": "TG",
    "Tessin": "TI",
    "Vaud": "VD",
    "Valais": "VS",
    "Neuchâtel": "NE",
    "Genève": "GE",
    "Jura": "JU",
}


def parse_swiss_price(text: str | None) -> int | None:
    """Format a Swiss price string into an integer representing the price in centimes."""
    if text is None:
        return None
    match = _PRICE.search(text)
    if match is None:
        return None
    francs = int(re.sub(r"[^\d]", "", match.group("francs")))
    cents_text = match.group("cents")
    cents = int(cents_text.ljust(2, "0")) if cents_text else 0
    return francs * 100 + cents


def parse_monthly_rent(text: str | None, surface_m2: float | None) -> int | None:
    """Monthly rent in centimes, whatever the period or unit the agency displays.

    « / an » is divided by 12; « / m² » is multiplied by the surface,
    and gives None without a surface rather than a per-m² amount posing as a rent.
    A rent of zero (« CHF 0.- / mois ») is no price: None, never 0.
    """
    amount = parse_swiss_price(text)
    if not amount or text is None:
        return None
    monthly: float = amount
    if _PER_M2.search(text):
        if surface_m2 is None:
            return None
        monthly *= surface_m2
    if _is_yearly(text):
        monthly /= 12
    return round(monthly)


def parse_charges(
    text: str | None, rent: str | None, price_chf: int | None
) -> int | None:
    """Monthly charges in centimes, None unless they go with a known, monthly rent.

    Agencies show charges without a unit: next to the rent line `rent` of a
    yearly or per-m² rent, or of a rent on request (`price_chf` is None), nothing
    says what they are worth per month. Charges of zero are no charges: None.
    """
    if price_chf is None or rent is None or not is_monthly_rent(rent):
        return None
    return parse_swiss_price(text) or None


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


def canton_code(canton: str | None) -> str | None:
    """Return the Swiss abbreviation for a canton name, if it is recognized."""
    if not canton:
        return None
    code = CANTON_TO_ABR.get(canton)
    if code is None:
        logger.warning("Unknown canton name %r", canton)
    return code


def parse_surface(text: str | None) -> float | None:
    """Format a Swiss surface string into a float representing the surface in square meters."""
    if text is None:
        return None
    bare = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*", text)
    if bare:
        return float(bare.group(1))
    match = re.search(
        r"(\d+(?:\.\d+)?)\s*(?:m²|m2|sqm|square meters?)",
        text,
        re.IGNORECASE,
    )
    if match:
        return float(match.group(1))
    return None


def parse_floor(text: str | None) -> int | None:
    """Floor named in a French text, None when no floor is named.

    « 2ème étage » is 2, « rez-de-chaussée » or « rez-supérieur » 0, « 1er sous-sol » -1.
    A floor given alone, as in a details table, counts too: « 7ème » is 7, « -1 » -1.
    """
    if bare := _BARE_FLOOR.fullmatch(text or ""):
        return int(bare[1])
    match = _FLOOR.search(text or "")
    if match is None:
        return None
    if match["ground"]:
        return 0
    if match["basement"]:
        return -int(match["basement"])
    return int(match["floor"])


def parse_property_type(text: str | None) -> PropertyType | None:
    """PropertyType of the label `text` starts with, None for an unknown label.

    « Appartement 3.0 pièces » is APARTMENT, « Dépôt » STORAGE, « Château » None.
    """
    if not text:
        return None
    match = _PROPERTY_TYPE.match(text)
    if match is None:
        logger.warning("Unknown property type label %r", text)
        return None
    return _PROPERTY_TYPES[match[1].lower()]


def is_monthly_rent(text: str) -> bool:
    """Whether a rent line is monthly: no yearly period (unless « / mois ») and no per-m² unit.

    Agencies show charges without a unit; they can only be added to a monthly rent.
    """
    return not _PER_M2.search(text) and not _is_yearly(text)


def _is_yearly(text: str) -> bool:
    """Whether a rent line gives a yearly amount: « / an », and no « / mois »."""
    return bool(_PER_YEAR.search(text)) and not _PER_MONTH.search(text)
