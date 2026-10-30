"""Instrument metadata and deterministic synthetic 1-minute OHLCV. Never market observations.

Generation uses only seeded integer-tick arithmetic, so the same spec reproduces identical
candles on any platform. Anything a backtest consumes is a `MarketData`: candles carrying
explicit availability, a cash-session calendar and a content hash.
"""

import random
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from quantlab.data.model import SECOND, DataError, canonical, digest, token
from quantlab.strategies.calendar import MINUTE_NS, Calendar, SessionSpec
from quantlab.strategies.market import Candle


@dataclass(frozen=True, slots=True)
class InstrumentSpec:
    """Metadata only; strategies never infer tick, lot or multiplier from a symbol."""

    symbol: str
    venue: str
    kind: str  # "equity" (multiplier 1) or "future"
    currency: str
    tick: Decimal
    multiplier: int
    lot: int

    def __post_init__(self) -> None:
        token(self.symbol)
        token(self.venue)
        if self.kind not in ("equity", "future") or self.currency != "USD":
            raise DataError("kind must be equity|future and currency USD (no FX model)")
        if self.tick <= 0 or self.lot < 1 or self.multiplier < 1:
            raise DataError("tick, lot and multiplier must be positive")
        if self.kind == "equity" and self.multiplier != 1:
            raise DataError("equities have multiplier 1")

    @property
    def id(self) -> str:
        return f"{self.symbol}.{self.venue}"

    @property
    def precision(self) -> int:
        return max(0, -int(self.tick.as_tuple().exponent))


@dataclass(frozen=True, slots=True)
class SyntheticSpec:
    """Seeded random walk in whole ticks with overnight gaps; `delay_seconds` is the modeled
    time between a minute completing and its candle becoming usable."""

    seed: int
    start_day: str
    sessions: int
    open_price: Decimal
    step_ticks: int
    wick_ticks: int
    gap_ticks: int
    volume: int
    delay_seconds: int
    early_close_days: tuple[str, ...] = ()
    holidays: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        date.fromisoformat(self.start_day)
        if not 1 <= self.sessions <= 600 or self.open_price <= 0:
            raise DataError("1 to 600 sessions and a positive open price required")
        if min(self.step_ticks, self.wick_ticks, self.gap_ticks) < 0 or self.volume < 2:
            raise DataError("tick moves cannot be negative and volume must be at least 2")
        if not 0 <= self.delay_seconds < 60:
            raise DataError("availability delay must be under one minute")
        for d in (*self.early_close_days, *self.holidays):
            date.fromisoformat(d)


@dataclass(frozen=True, slots=True)
class MarketData:
    instrument: InstrumentSpec
    calendar: Calendar
    candles: tuple[Candle, ...]
    sha256: str

    @classmethod
    def build(
        cls, instrument: InstrumentSpec, calendar: Calendar, candles: tuple[Candle, ...]
    ) -> "MarketData":
        pairs = zip(candles, candles[1:], strict=False)
        if not candles or any(b.start < a.end or b.available < a.available for a, b in pairs):
            raise DataError("candles must be non-empty, ordered and non-overlapping")
        rows = [
            [c.start, c.end, c.available, str(c.open), str(c.high), str(c.low), str(c.close)]
            + [c.volume, c.day]
            for c in candles
        ]
        meta = [instrument.id, str(instrument.tick), instrument.multiplier, instrument.lot]
        sessions = [[s.day, s.cash_close] for s in calendar.sessions]
        return cls(
            instrument, calendar, candles, digest(canonical({"m": meta, "s": sessions, "c": rows}))
        )


def sessions_from(spec: SyntheticSpec) -> Calendar:
    days: list[SessionSpec] = []
    current = date.fromisoformat(spec.start_day)
    while len(days) < spec.sessions:
        iso = current.isoformat()
        if current.weekday() < 5 and iso not in spec.holidays:
            days.append(SessionSpec(iso, "13:00" if iso in spec.early_close_days else "16:00"))
        current += timedelta(days=1)
    return Calendar(tuple(days))


def generate(spec: SyntheticSpec, instrument: InstrumentSpec) -> MarketData:
    """Deterministic candles: price = whole ticks, prior close carries into the next open."""
    rng = random.Random(spec.seed)
    calendar = sessions_from(spec)
    tick = instrument.tick
    price = max(int(spec.open_price / tick), 20)
    delay = spec.delay_seconds * SECOND
    candles: list[Candle] = []
    for session in calendar.sessions:
        price = max(price + rng.randint(-spec.gap_ticks, spec.gap_ticks), 20)
        for start in range(session.open, session.close, MINUTE_NS):
            open_t = price
            price = max(open_t + rng.randint(-spec.step_ticks, spec.step_ticks), 20)
            high = max(open_t, price) + rng.randint(0, spec.wick_ticks)
            low = max(min(open_t, price) - rng.randint(0, spec.wick_ticks), 1)
            volume = spec.volume + rng.randint(0, spec.volume // 2)
            end = start + MINUTE_NS
            candles.append(
                Candle(
                    start,
                    end,
                    end + delay,
                    open_t * tick,
                    high * tick,
                    low * tick,
                    price * tick,
                    volume,
                    session.day,
                )
            )
    return MarketData.build(instrument, calendar, tuple(candles))
