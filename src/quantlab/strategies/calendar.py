"""Cash-session calendar: explicit open/close per trade date, never inferred from bars."""

from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field

from quantlab.data.model import DataError, local_ns

MINUTE_NS = 60_000_000_000


@dataclass(frozen=True, slots=True)
class SessionSpec:
    """One US cash session in New York time; early closes are listed explicitly."""

    day: str
    cash_close: str = "16:00"

    @property
    def open(self) -> int:
        return local_ns(self.day, "09:30")

    @property
    def close(self) -> int:
        return local_ns(self.day, self.cash_close)

    @property
    def full(self) -> bool:
        return self.cash_close == "16:00"

    def __post_init__(self) -> None:
        if self.cash_close not in ("13:00", "16:00"):
            raise DataError("unsupported cash close")


@dataclass(frozen=True, slots=True)
class Calendar:
    sessions: tuple[SessionSpec, ...]
    _by_day: dict[str, SessionSpec] = field(init=False, repr=False, compare=False)
    _days: tuple[str, ...] = field(init=False, repr=False, compare=False)
    _opens: tuple[int, ...] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        days = [s.day for s in self.sessions]
        if days != sorted(set(days)) or not days:
            raise DataError("calendar needs unique chronological sessions")
        object.__setattr__(self, "_by_day", {s.day: s for s in self.sessions})
        object.__setattr__(self, "_days", tuple(days))
        object.__setattr__(self, "_opens", tuple(s.open for s in self.sessions))

    def get(self, day: str) -> SessionSpec | None:
        return self._by_day.get(day)

    def previous(self, day: str) -> SessionSpec | None:
        i = bisect_left(self._days, day)
        return self.sessions[i - 1] if i else None

    def containing(self, ns: int) -> SessionSpec | None:
        """Session whose [open, close] window contains the instant, if any."""
        i = bisect_right(self._opens, ns) - 1
        if i >= 0 and ns <= self.sessions[i].close:
            return self.sessions[i]
        return None
