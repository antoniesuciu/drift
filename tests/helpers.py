"""Scripted-data builders shared by strategy and backtest tests (synthetic only)."""

from decimal import Decimal
from typing import Any

from drift.backtest.config import BacktestConfig, default_config
from drift.backtest.data import InstrumentSpec, MarketData
from drift.data.model import SECOND, local_ns
from drift.strategies.calendar import MINUTE_NS, Calendar, SessionSpec
from drift.strategies.market import Candle

DAY = "2022-03-08"


def clock(minutes_after_open: int) -> str:
    total = 9 * 60 + 30 + minutes_after_open
    return f"{total // 60:02d}:{total % 60:02d}"


def day_candles(
    day: str,
    cash_close: str = "16:00",
    default: str = "100.00",
    at: dict[str, Any] | None = None,
    delay: int = 1,
    volume: int = 1000,
) -> list[Candle]:
    """Flat 1-minute candles for one session.

    `at` maps the clock at which a minute ENDS to its price: one string (flat candle),
    (o, h, l, c) or (o, h, l, c, volume). Everything else is flat at `default`.
    """
    session = SessionSpec(day, cash_close)
    out = []
    for i, start in enumerate(range(session.open, session.close, MINUTE_NS)):
        value = (at or {}).get(clock(i + 1), default)
        row = (value,) * 4 if isinstance(value, str) else tuple(value)
        vol = row[4] if len(row) == 5 else volume
        o, h, low, c = (Decimal(x) for x in row[:4])
        end = start + MINUTE_NS
        out.append(Candle(start, end, end + delay * SECOND, o, h, low, c, vol, day))
    return out


def merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merge(out[key], value)
        else:
            out[key] = value
    return out


def make_config(strategy: str = "itsm", /, **patch: Any) -> BacktestConfig:
    return BacktestConfig.parse(merge(default_config(strategy), patch))


def scripted_market(
    instrument: InstrumentSpec,
    sessions: list[tuple[str, str, dict[str, Any]]],
    default: str = "100.00",
    delay: int = 1,
) -> MarketData:
    """sessions: (day, cash_close, `at` overrides)."""
    calendar = Calendar(tuple(SessionSpec(d, c) for d, c, _ in sessions))
    candles = [k for d, c, at in sessions for k in day_candles(d, c, default, at, delay)]
    return MarketData.build(instrument, calendar, tuple(candles))


def start_of(day: str, hhmm: str) -> int:
    return local_ns(day, hhmm)


def bar(o: str, h: str, low: str, c: str, i: int = 0, volume: int = 1000, day: str = DAY) -> Candle:
    """A 1-minute candle at minute index `i` after the open, available one second later."""
    start = start_of(day, "09:30") + i * MINUTE_NS
    end = start + MINUTE_NS
    return Candle(
        start, end, end + SECOND, Decimal(o), Decimal(h), Decimal(low), Decimal(c), volume, day
    )


WEEK = ["2022-03-07", "2022-03-08", "2022-03-09", "2022-03-10", "2022-03-11"]


def calendar_of(*days: str, early: tuple[str, ...] = ()) -> Calendar:
    return Calendar(tuple(SessionSpec(d, "13:00" if d in early else "16:00") for d in days))


def feed_all(rule: Any, candles: list[Candle]) -> list[Any]:
    """Push candles in order and collect every proposal the rule emits."""
    return [p for c in candles if (p := rule.on_candle(c)) is not None]


EQUITY = InstrumentSpec("SYNTH", "XNAS", "equity", "USD", Decimal("0.01"), 1, 1)


def walk(seed: int = 3, sessions: int = 3, step_ticks: int = 8, gap_ticks: int = 40) -> MarketData:
    """Seeded synthetic random-walk sessions for differential tests."""
    from drift.backtest.data import SyntheticSpec, generate

    spec = SyntheticSpec(
        seed=seed,
        start_day="2022-03-07",
        sessions=sessions,
        open_price=Decimal("100.00"),
        step_ticks=step_ticks,
        wick_ticks=2,
        gap_ticks=gap_ticks,
        volume=1000,
        delay_seconds=1,
    )
    return generate(spec, EQUITY)
