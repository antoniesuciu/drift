"""Causal per-session state shared by the rule models.

`SessionTape` is fed completed candles in order and exposes only what is knowable at the
latest candle: the current session so far (opening range, VWAP and its dispersion, gap flag)
and summaries of sessions that have already ended (daily range, true range, ATR). A session
becomes history only when the next session's first candle arrives, so nothing here can leak
the future. The module holds no trading policy.
"""

import re
from collections import deque
from dataclasses import dataclass
from decimal import Decimal

from quantlab.data.model import DataError
from quantlab.strategies.calendar import MINUTE_NS, Calendar, SessionSpec
from quantlab.strategies.market import Candle

_CLOCK = re.compile(r"(?:0\d|1\d|2[0-3]):[0-5]\d")
KEEP_DAYS = 64  # ended sessions retained; bounds every lookback that reads `SessionTape.days`


def check_clock(value: str) -> str:
    """HH:MM within the cash session (09:30 < t < 16:00), as a New York wall-clock time."""
    if not _CLOCK.fullmatch(value) or not "09:30" < value < "16:00":
        raise DataError("clock must be HH:MM strictly inside the 09:30-16:00 cash session")
    return value


@dataclass(frozen=True, slots=True)
class DaySummary:
    day: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    complete: bool  # a full cash session with every minute present


class SessionTape:
    def __init__(self, calendar: Calendar, keep_days: int = KEEP_DAYS) -> None:
        self.calendar = calendar
        self.days: deque[DaySummary] = deque(maxlen=keep_days)
        self.session: SessionSpec | None = None
        self.today: list[Candle] = []
        self.clean = True  # no missing minute since the open
        self._last_end = 0
        self._by_end: dict[int, Candle] = {}
        self._v = self._pv = self._pv2 = Decimal(0)

    def push(self, c: Candle) -> bool:
        """Add a candle; True when it opens a new session (history just advanced)."""
        if c.start < self._last_end:
            raise DataError("candles must be ordered and non-overlapping")
        self._last_end = c.end
        fresh = self.session is None or c.day != self.session.day
        if fresh:
            self._finish()
            session = self.calendar.get(c.day)
            if session is None or c.start < session.open or c.end > session.close:
                raise DataError("candle outside its classified cash session")
            self.session, self.today, self._by_end, self.clean = session, [], {}, True
            self._v = self._pv = self._pv2 = Decimal(0)
        expected = self.today[-1].end if self.today else (self.session.open if self.session else 0)
        if c.start != expected:
            self.clean = False
        self.today.append(c)
        self._by_end[c.end] = c
        typical = (c.high + c.low + c.close) / 3
        self._v += c.volume
        self._pv += c.volume * typical
        self._pv2 += c.volume * typical * typical
        return fresh

    def _finish(self) -> None:
        if not self.today or self.session is None:
            return
        s = self.session
        minutes = (s.close - s.open) // MINUTE_NS
        self.days.append(
            DaySummary(
                s.day,
                self.today[0].open,
                max(c.high for c in self.today),
                min(c.low for c in self.today),
                self.today[-1].close,
                sum(c.volume for c in self.today),
                s.full and self.clean and len(self.today) == minutes,
            )
        )

    def at(self, end: int) -> Candle | None:
        return self._by_end.get(end)

    @property
    def vwap(self) -> Decimal | None:
        """Session VWAP of typical prices through the latest candle."""
        return self._pv / self._v if self._v > 0 else None

    @property
    def vwap_std(self) -> Decimal | None:
        """Volume-weighted standard deviation of typical price around the session VWAP."""
        if self._v <= 0:
            return None
        mean = self._pv / self._v
        return max(self._pv2 / self._v - mean * mean, Decimal(0)).sqrt()

    def true_ranges(self, n: int) -> list[Decimal] | None:
        """True ranges of the last `n` ended sessions; None unless history is complete."""
        if len(self.days) < n + 1:
            return None
        recent = list(self.days)[-(n + 1) :]
        if not all(d.complete for d in recent):
            return None
        return [
            max(b.high - b.low, abs(b.high - a.close), abs(b.low - a.close))
            for a, b in zip(recent, recent[1:], strict=False)
        ]

    def prior_true_range_vs_atr(self, n: int) -> tuple[Decimal, Decimal] | None:
        """(yesterday's true range, n-session ATR ending yesterday), or None if unavailable."""
        ranges = self.true_ranges(n)
        return None if ranges is None else (ranges[-1], sum(ranges, Decimal(0)) / n)
