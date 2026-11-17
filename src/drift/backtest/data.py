"""Instrument metadata, shared historical/synthetic candles and native bar conversion.

Generation uses only seeded integer-tick arithmetic, so the same spec reproduces identical
candles on any platform; generated prices are never market observations. A backtest consumes
`MarketData`: candles carrying
explicit availability, a cash-session calendar and a content hash.
"""

import random
import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from drift.data.model import SECOND, DataError, canonical, digest, token
from drift.strategies.calendar import MINUTE_NS, Calendar, SessionSpec
from drift.strategies.market import Candle


def research_role(day: str) -> str:
    """Frozen split of an ISO day or month: never decided by a caller."""
    return "development" if day < "2023" else "validation" if day < "2024" else "holdout"


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
    data_precision: int | None = None

    def __post_init__(self) -> None:
        token(self.symbol)
        token(self.venue)
        if self.kind not in ("equity", "future") or self.currency != "USD":
            raise DataError("kind must be equity|future and currency USD (no FX model)")
        if self.tick <= 0 or self.lot < 1 or self.multiplier < 1:
            raise DataError("tick, lot and multiplier must be positive")
        if self.kind == "equity" and self.multiplier != 1:
            raise DataError("equities have multiplier 1")
        if self.data_precision is not None and (
            type(self.data_precision) is not int
            or not max(0, -int(self.tick.as_tuple().exponent)) <= self.data_precision <= 9
        ):
            raise DataError("data precision must preserve the tick and be at most 9")

    @property
    def id(self) -> str:
        return f"{self.symbol}.{self.venue}"

    @property
    def precision(self) -> int:
        return self.data_precision or max(0, -int(self.tick.as_tuple().exponent))


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
class HistoricalSpec:
    dataset_id: str

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[0-9a-f]{64}", self.dataset_id):
            raise DataError("historical data must reference an immutable dataset ID")


@dataclass(frozen=True, slots=True)
class MarketData:
    instrument: InstrumentSpec
    calendar: Calendar
    candles: tuple[Candle, ...]
    sha256: str
    source_ref: str | None = None
    source_feed: str | None = None

    @classmethod
    def build(
        cls,
        instrument: InstrumentSpec,
        calendar: Calendar,
        candles: tuple[Candle, ...],
        *,
        source_ref: str | None = None,
        source_feed: str | None = None,
    ) -> "MarketData":
        pairs = zip(candles, candles[1:], strict=False)
        if not candles or any(b.start < a.end or b.available < a.available for a, b in pairs):
            raise DataError("candles must be non-empty, ordered and non-overlapping")
        rows = [
            [c.start, c.end, c.available, str(c.open), str(c.high), str(c.low), str(c.close)]
            + [c.volume, c.day]
            for c in candles
        ]
        meta = [
            instrument.id,
            str(instrument.tick),
            instrument.multiplier,
            instrument.lot,
            instrument.kind,
            instrument.currency,
            instrument.precision,
        ]
        sessions = [[s.day, s.cash_close] for s in calendar.sessions]
        return cls(
            instrument,
            calendar,
            candles,
            digest(canonical({"m": meta, "s": sessions, "c": rows, "source": source_ref})),
            source_ref,
            source_feed,
        )


def native_bars(data: MarketData) -> list[Any]:
    """The same native representation is stored and fed to the backtest engine."""
    from nautilus_trader.model.data import Bar, BarType
    from nautilus_trader.model.objects import Price, Quantity

    bar_type = BarType.from_str(f"{data.instrument.id}-1-MINUTE-LAST-EXTERNAL")
    precision = data.instrument.precision
    quantum = Decimal(1).scaleb(-precision)
    if any(p % quantum for c in data.candles for p in (c.open, c.high, c.low, c.close)):
        raise DataError("native conversion would round observed prices")
    return [
        Bar(
            bar_type,
            *(
                Price.from_str(format(p, f".{precision}f"))
                for p in (c.open, c.high, c.low, c.close)
            ),
            Quantity.from_int(c.volume),
            c.end,
            c.available,
        )
        for c in data.candles
    ]


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
