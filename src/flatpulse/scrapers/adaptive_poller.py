"""Adaptive polling: how long to wait before polling a source again (#47).

The interval starts from the source's `poll_interval_s` and is scaled by its
recent activity, its errors and the time of day, then kept within 30-600 s:

- active (more than 5 new listings in the last hour): halved, to alert sooner;
- inactive (no new listing in six hours): doubled, to spare a dead source;
- n consecutive errors: multiplied by 2ⁿ, so a site down is not hammered;
- outside office hours (night, weekend): tripled, agencies publish during the day.
"""

from collections.abc import Callable
from datetime import datetime
from zoneinfo import ZoneInfo

from flatpulse.common.models import ScrapingStats, SourceConfig

ZURICH = ZoneInfo("Europe/Zurich")

MIN_INTERVAL_S = 30
MAX_INTERVAL_S = 600
ACTIVE_LISTINGS_PER_HOUR = 5
OFFICE_HOURS = range(7, 20)  # 07:00-19:59, Swiss time
WEEKEND = {5, 6}  # Saturday, Sunday (`datetime.weekday()`)
OFF_HOURS_FACTOR = 3
# Beyond 2⁶⁴ any interval is far past the cap; the bound keeps 2ⁿ a float.
MAX_BACKOFF_EXPONENT = 64


def _now_in_zurich() -> datetime:
    """The current time in Switzerland."""
    return datetime.now(ZURICH)


class AdaptivePoller:
    """Computes the next polling interval of a source from its scraping stats."""

    def __init__(self, clock: Callable[[], datetime] = _now_in_zurich) -> None:
        """Read the time from `clock`, Swiss time by default."""
        self._clock = clock

    def compute_interval(
        self, source_config: SourceConfig, stats: ScrapingStats
    ) -> int:
        """Seconds to wait before polling `source_config` again, within 30-600 s."""
        factor = 1.0
        if stats.new_listings_last_hour > ACTIVE_LISTINGS_PER_HOUR:
            factor /= 2
        elif stats.new_listings_last_6h == 0:
            factor *= 2
        factor *= 2.0 ** min(stats.consecutive_errors, MAX_BACKOFF_EXPONENT)
        if self._is_off_hours():
            factor *= OFF_HOURS_FACTOR
        interval = round(source_config.poll_interval_s * factor)
        return min(max(interval, MIN_INTERVAL_S), MAX_INTERVAL_S)

    def _is_off_hours(self) -> bool:
        """Whether it is night or weekend in Switzerland."""
        now = self._clock().astimezone(ZURICH)
        return now.weekday() in WEEKEND or now.hour not in OFFICE_HOURS
