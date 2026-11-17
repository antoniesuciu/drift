"""Market data for the runner. Sources refuse a gap in coverage; they never fill one.

A source is a small picklable value, so each worker process rebuilds exactly what it needs.
`verify` does the expensive proof once per batch; `load` is then cheap enough for every worker.
"""

import json
from dataclasses import dataclass, replace
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol

import pyarrow as pa
import pyarrow.parquet as pq

from drift.backtest.config import plain
from drift.backtest.data import InstrumentSpec, MarketData, SyntheticSpec, generate
from drift.data.history import months, partitions
from drift.data.model import DataError, canonical, digest
from drift.data.store import safe_file
from drift.research.scope import Interval
from drift.strategies.calendar import Calendar, SessionSpec
from drift.strategies.market import Candle

# Fixed across every interval: a price's text must not depend on which months were loaded.
_ARCHIVE_PRECISION = 6
_COLUMNS = ("start_ns", "end_ns", "available_ns", "open", "high", "low", "close", "volume")


@dataclass(frozen=True, slots=True)
class Piece:
    """Candles for one window, plus what a configuration must state about them."""

    data: MarketData
    config: dict[str, Any]  # the version/synthetic/data part of a BacktestConfig
    splits: tuple[tuple[str, str], ...] = ()
    gaps: tuple[tuple[str, int], ...] = ()  # (day, missing minutes), for days with any


class MarketDataSource(Protocol):
    @property
    def historical(self) -> bool: ...

    def verify(self, interval: Interval) -> None:
        """Prove the window's data, or raise. Runs once per batch, before any worker."""

    def load(self, interval: Interval) -> Piece:
        """The window's candles, or raise when any part of it is unavailable."""


def _trusted(root: Path, row: dict[str, Any]) -> tuple[dict[str, Any], bytes, dict[str, Any]]:
    """A month's manifest, Parquet bytes and quality report, each hash-checked."""
    folder = safe_file(root, row["dataset"] + "/manifest.json").parent
    body = (folder / "manifest.json").read_bytes()
    manifest = json.loads(body)
    bars, quality = (folder / "bars.parquet").read_bytes(), (folder / "quality.json").read_bytes()
    if (
        (folder / "COMPLETE").read_text() != digest(body)
        or manifest["dataset_id"] != row["dataset_id"]
        or manifest["inventory"]["bars.parquet"] != digest(bars)
        or manifest["inventory"]["quality.json"] != digest(quality)
    ):
        raise DataError("archive partition differs from its manifest")
    return manifest, bars, json.loads(quality)


def _candles(bars: bytes, interval: Interval) -> list[Candle]:
    columns = pq.read_table(pa.BufferReader(bars), columns=[*_COLUMNS, "session_date"]).to_pydict()
    rows = zip(*(columns[name] for name in (*_COLUMNS, "session_date")), strict=True)
    return [
        Candle(start, end, available, o, h, low, c, volume, day)
        for start, end, available, o, h, low, c, volume, day in rows
        if interval.start <= day <= interval.end
    ]


@dataclass(frozen=True, slots=True)
class ArchiveSource:
    """The verified monthly NVDA archive (`docs/data/NVDA_HISTORY.md`), raw SIP minutes."""

    root: Path

    @property
    def historical(self) -> bool:
        return True

    def _rows(self, interval: Interval) -> list[dict[str, Any]]:
        wanted = months(interval.start[:7], interval.end[:7])
        if not (self.root / "index.json").is_file():
            raise DataError(f"no archive index under {self.root}")
        rows = {
            r["month"]: r for r in json.loads((self.root / "index.json").read_bytes())["months"]
        }
        absent = [month for month in wanted if month not in rows]
        if absent:
            raise DataError(f"archive has no data for {absent[0]}; nothing is substituted")
        return [rows[month] for month in wanted]

    def verify(self, interval: Interval) -> None:
        partitions(self.root, selected={r["month"] for r in self._rows(interval)})

    def load(self, interval: Interval) -> Piece:
        ids: list[str] = []
        candles: list[Candle] = []
        sessions: list[SessionSpec] = []
        splits: list[tuple[str, str]] = []
        gaps: list[tuple[str, int]] = []
        instrument: InstrumentSpec | None = None
        for row in self._rows(interval):
            manifest, bars, quality = _trusted(self.root, row)
            spec = InstrumentSpec(
                **manifest["instrument"] | {"tick": Decimal(manifest["instrument"]["tick"])}
            )
            spec = replace(spec, data_precision=_ARCHIVE_PRECISION)
            if instrument is not None and spec != instrument:
                raise DataError("archive months disagree on the instrument")
            instrument = spec
            ids.append(row["dataset_id"])
            candles += _candles(bars, interval)
            inside = [s for s in quality["sessions"] if interval.start <= s["day"] <= interval.end]
            sessions += [
                SessionSpec(s["day"], "16:00" if s["expected"] == 390 else "13:00") for s in inside
            ]
            gaps += [(s["day"], len(s["missing_starts"])) for s in inside if s["missing_starts"]]
            splits += [
                (s["day"], str(s["ratio"]))
                for s in manifest["splits"]
                if interval.start <= s["day"] <= interval.end
            ]
        if not candles or instrument is None:
            raise DataError("no sessions in the requested interval")
        reference = digest(canonical([ids, sessions[0].day, sessions[-1].day]))
        data = MarketData.build(
            instrument,
            Calendar(tuple(sessions)),
            tuple(candles),
            source_ref=reference,
            source_feed="sip",
        )
        fragment = {"version": 2, "synthetic": False, "data": {"dataset_id": reference}}
        return Piece(data, fragment, tuple(splits), tuple(gaps))


@dataclass(frozen=True, slots=True)
class SyntheticSource:
    """Seeded candles for tests and demos; never market observations."""

    spec: SyntheticSpec
    instrument: InstrumentSpec

    @property
    def historical(self) -> bool:
        return False

    def verify(self, interval: Interval) -> None:
        return None

    def load(self, interval: Interval) -> Piece:
        whole = generate(self.spec, self.instrument)
        candles = tuple(c for c in whole.candles if interval.start <= c.day <= interval.end)
        if not candles or interval.end > whole.candles[-1].day:
            raise DataError("synthetic data does not cover the requested interval")
        days = {c.day for c in candles}
        calendar = Calendar(tuple(s for s in whole.calendar.sessions if s.day in days))
        fragment = {"version": 1, "synthetic": True, "data": plain(self.spec)}
        return Piece(MarketData.build(self.instrument, calendar, candles), fragment)
