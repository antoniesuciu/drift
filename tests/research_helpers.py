"""Shared fixtures for the research runner's tests (synthetic only)."""

from dataclasses import dataclass, replace
from decimal import Decimal
from pathlib import Path
from typing import Any

from helpers import scripted_market

from drift.backtest.config import plain
from drift.backtest.data import InstrumentSpec, MarketData, SyntheticSpec
from drift.research.runner import RunJob
from drift.research.scope import Interval
from drift.research.settings import apply_overrides, default_settings, parse_override
from drift.research.sources import Piece, SyntheticSource
from drift.strategies.calendar import Calendar

EQUITY = InstrumentSpec("SYNTH", "XNAS", "equity", "USD", Decimal("0.01"), 1, 1)
SPEC = SyntheticSpec(7, "2022-03-07", 12, Decimal("100.00"), 4, 2, 60, 1000, 1)
SOURCE = SyntheticSource(SPEC, EQUITY)
# Six decimals, like the real archive: bps offsets then land between cents.
PRECISE = SyntheticSource(SPEC, replace(EQUITY, data_precision=6))
FIRST, MIDDLE, NEXT, LAST = "2022-03-07", "2022-03-14", "2022-03-15", "2022-03-22"
WINDOW = Interval(FIRST, LAST)
PLUGIN = ("research_plugin",)


def settings(strategy: str, *overrides: str, **kwargs: Any) -> dict[str, Any]:
    pairs = [parse_override(text) for text in overrides]
    return apply_overrides(default_settings(strategy, **kwargs), strategy, pairs)


def job(store: Path, strategy: str, *overrides: str, window: Interval = WINDOW, **kwargs: Any):
    return RunJob(
        strategy,
        settings(strategy, *overrides, **kwargs),
        window,
        SOURCE,
        store,
        ("synthetic",),
        None,
        PLUGIN,
    )


@dataclass(frozen=True, slots=True)
class ScriptedSource:
    """Hand-written candles, a third adapter at the data seam."""

    rows: tuple[tuple[str, str, dict[str, Any]], ...]
    gaps: tuple[tuple[str, int], ...] = ()

    @property
    def historical(self) -> bool:
        return False

    def verify(self, interval: Interval) -> None:
        return None

    def load(self, interval: Interval) -> Piece:
        rows = [r for r in self.rows if interval.start <= r[0] <= interval.end]
        whole: MarketData = scripted_market(EQUITY, rows)
        calendar = Calendar(whole.calendar.sessions)
        data = MarketData.build(EQUITY, calendar, whole.candles)
        fragment = {"version": 1, "synthetic": True, "data": plain(SPEC)}
        gaps = tuple(g for g in self.gaps if interval.start <= g[0] <= interval.end)
        return Piece(data, fragment, gaps=gaps)
