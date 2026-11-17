"""Provider-neutral market observations shared by every strategy family.

A `Candle` is a completed bar with an explicit availability time; nothing may use it before
`available`. `Aggregator` builds higher timeframes only from complete, available minutes.
"""

from dataclasses import dataclass, field
from decimal import Decimal

from drift.data.model import DataError
from drift.strategies.calendar import MINUTE_NS, Calendar

TIMEFRAMES = (1, 5, 15, 30, 60)


@dataclass(frozen=True, slots=True)
class Candle:
    """A completed bar: `start`/`end` bound the observation, `available` gates its use."""

    start: int
    end: int
    available: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    day: str

    def __post_init__(self) -> None:
        prices = (self.open, self.high, self.low, self.close)
        if not all(isinstance(p, Decimal) and p.is_finite() for p in prices):
            raise DataError("candle prices must be finite decimals")
        if not 0 < self.low <= min(self.open, self.close):
            raise DataError("invalid candle OHLC")
        if not max(self.open, self.close) <= self.high:
            raise DataError("invalid candle OHLC")
        if self.end <= self.start or self.available < self.end or self.volume < 0:
            raise DataError("invalid candle timing or volume")

    @property
    def body(self) -> Decimal:
        return abs(self.close - self.open)

    @property
    def range(self) -> Decimal:
        return self.high - self.low

    @property
    def upper(self) -> Decimal:
        return self.high - max(self.open, self.close)

    @property
    def lower(self) -> Decimal:
        return min(self.open, self.close) - self.low

    @property
    def bullish(self) -> bool:
        return self.close > self.open

    @property
    def bearish(self) -> bool:
        return self.close < self.open


@dataclass(slots=True)
class Aggregator:
    """1-minute candles to a full timeframe bucket anchored at the session open.

    A bucket is published only when its last constituent arrives and every minute in it is
    present; truncated end-of-session buckets and any bucket with a gap are never published
    (counted in `incomplete`). Availability is the latest constituent availability.
    """

    minutes: int
    calendar: Calendar
    incomplete: int = 0
    _bucket: list[Candle] = field(default_factory=list)
    _last_end: int = 0
    _dead: int = -1  # origin of a bucket already known to be unusable

    def __post_init__(self) -> None:
        if self.minutes not in TIMEFRAMES:
            raise DataError("unsupported timeframe")

    def push(self, c: Candle) -> Candle | None:
        if c.end - c.start != MINUTE_NS or c.start < self._last_end:
            raise DataError("aggregator needs ordered, non-overlapping 1-minute candles")
        self._last_end = c.end
        if self.minutes == 1:
            return c
        session = self.calendar.get(c.day)
        if session is None or c.start < session.open or c.end > session.close:
            raise DataError("candle outside its classified cash session")
        width = self.minutes * MINUTE_NS
        origin = session.open + (c.start - session.open) // width * width
        if self._bucket and self._bucket[0].start < origin:
            self.incomplete += 1  # the previous bucket ended without completing
            self._bucket = []
        if origin == self._dead:
            return None
        if self._bucket and self._bucket[-1].end != c.start:
            self.incomplete += 1  # gap inside the bucket
            self._bucket, self._dead = [], origin
            return None
        if not self._bucket and c.start != origin:
            self.incomplete += 1  # the bucket's first minute is missing
            self._dead = origin
            return None
        self._bucket.append(c)
        if c.end != origin + width:
            return None
        parts, self._bucket = self._bucket, []
        return Candle(
            parts[0].start,
            c.end,
            max(p.available for p in parts),
            parts[0].open,
            max(p.high for p in parts),
            min(p.low for p in parts),
            c.close,
            sum(p.volume for p in parts),
            c.day,
        )
