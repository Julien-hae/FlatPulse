"""In-memory deduplication of scraped listings (#46).

A listing is identified by `source_slug:external_id`, never by its URL alone: two
agencies may share an id scheme, and some agencies' pages differ only by their query
string. Its fingerprint (`Listing.fingerprint`) tells whether it changed since the
last poll: a new price gives a new fingerprint.

The pipeline asks, for each scraped listing, `is_new(...) or has_changed(...)`: a
duplicate answers False to both and goes no further, so it costs no LLM quota.
"""

from flatpulse.common.models import Listing


class DeduplicationService:
    """Remembers the fingerprint of every listing seen, per source and external id.

    A dict in memory for the MVP: a restart forgets it, and the database's
    `UNIQUE (source_id, external_id)` remains the durable guard.
    """

    def __init__(self) -> None:
        """Start with no listing seen."""
        self._fingerprints: dict[str, str] = {}

    def is_new(self, listing: Listing, source_slug: str) -> bool:
        """Whether this source never published `listing`; it is then remembered.

        Asking twice for the same listing answers True, then False.
        """
        key = self._key(listing, source_slug)
        if key in self._fingerprints:
            return False
        self._fingerprints[key] = listing.fingerprint
        return True

    def has_changed(self, listing: Listing, source_slug: str) -> bool:
        """Whether a listing already seen has a new fingerprint; it is then remembered.

        A change is reported once, not on every following poll. A listing never seen
        has not changed: it is new.
        """
        key = self._key(listing, source_slug)
        known = self._fingerprints.get(key)
        if known is None or known == listing.fingerprint:
            return False
        self._fingerprints[key] = listing.fingerprint
        return True

    @staticmethod
    def _key(listing: Listing, source_slug: str) -> str:
        """The dedup key: `source_slug:external_id`."""
        return f"{source_slug}:{listing.external_id}"
