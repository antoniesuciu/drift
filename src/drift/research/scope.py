"""Backtest date windows and the gate in front of the frozen research split."""

from dataclasses import dataclass
from datetime import date

from drift.backtest.data import research_role
from drift.data.model import DataError


@dataclass(frozen=True, slots=True)
class Interval:
    """Inclusive ISO trade dates. Days, not instants: a run only ever holds whole sessions."""

    start: str
    end: str

    def __post_init__(self) -> None:
        try:
            first, last = date.fromisoformat(self.start), date.fromisoformat(self.end)
        except (TypeError, ValueError):
            raise DataError("interval dates must be YYYY-MM-DD") from None
        if (first.isoformat(), last.isoformat()) != (self.start, self.end) or first > last:
            raise DataError("interval dates must be YYYY-MM-DD and in order")

    @classmethod
    def select(cls, year: int | None, start: str | None, end: str | None) -> "Interval":
        """One calendar year, or an explicit inclusive start and end."""
        if year is not None and (start or end):
            raise DataError("choose --year or --start/--end, not both")
        if year is not None:
            return cls(f"{year:04d}-01-01", f"{year:04d}-12-31")
        if not start or not end:
            raise DataError("choose --year or both --start and --end")
        return cls(start, end)


def authorize(interval: Interval, *, allow_validation: bool = False) -> tuple[str, ...]:
    """Research roles this window may trade in, or refuse it.

    Development is open. Validation needs the caller's explicit opt-in, which the run records.
    Holdout cannot be unlocked here: its one-time use needs its own reviewed decision.
    """
    roles = tuple(dict.fromkeys(research_role(day) for day in (interval.start, interval.end)))
    if "holdout" in roles:
        raise DataError("holdout 2024-2025 is not available to backtests")
    if "validation" in roles and not allow_validation:
        raise DataError("validation 2023 needs an explicit --allow-validation")
    return roles
