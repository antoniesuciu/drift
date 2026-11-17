"""Explicit interval completion and availability, independent of any data vendor."""

from dataclasses import dataclass
from datetime import UTC, datetime


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware datetimes")
    normalized = value.astimezone(UTC)
    # ZoneInfo can attach an offset to an imaginary wall time during spring forward.
    if normalized.astimezone(value.tzinfo).replace(tzinfo=None) != value.replace(tzinfo=None):
        raise ValueError("timestamp is a nonexistent local wall time")
    return normalized


@dataclass(frozen=True, slots=True)
class BarInterval:
    """A bar's [start, end] observation window and earliest usable time.

    This represents timing only, not a calendar, market-data adapter or fill model.
    Inputs are normalized to UTC before comparison, including across DST folds.
    """

    start: datetime
    end: datetime
    available_at: datetime

    def __post_init__(self) -> None:
        for name in ("start", "end", "available_at"):
            object.__setattr__(self, name, _utc(getattr(self, name)))
        if self.end <= self.start:
            raise ValueError("bar end must follow start")
        if self.available_at < self.end:
            raise ValueError("a completed bar cannot be available before its end")

    def is_available_at(self, decision_time: datetime) -> bool:
        return _utc(decision_time) >= self.available_at
