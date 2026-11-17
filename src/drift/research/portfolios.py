"""Virtual portfolios: named, persistent accounts that only ever exist in simulation.

A portfolio binds one strategy to its own capital and a versioned configuration, and grows by
appending segments. Nothing about it reaches a broker. Continuation has one rule that makes it
correct: an agent's state is a pure function of its parameters and the candles it has seen, so
instead of serializing that state a segment replays the portfolio's whole candle history
through a fresh agent and trades only the new window. Cash and the high-water mark carry over;
the session counters reset at the boundary anyway.

That guarantee holds only under conditions checked here: the account ended flat with no order
that could still be live, the agent is replayable, the market history is byte-identical
and the code is unchanged. Otherwise a segment is refused, not approximated.
"""

import json
import re
import shutil
import tempfile
import time
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from drift.backtest.registry import strategy_entry
from drift.data.model import DataError, canonical, digest
from drift.research.metrics import compute, frame_of
from drift.research.records import Lineage
from drift.research.runner import RunJob, RunOutcome, code_version
from drift.research.scope import Interval, authorize
from drift.research.settings import apply_overrides, check_settings
from drift.research.sources import MarketDataSource
from drift.research.store import (
    PORTFOLIO_CONFIGS,
    PORTFOLIOS,
    SEGMENTS,
    ResultStore,
    write_new,
)

_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")


@dataclass(frozen=True, slots=True)
class Portfolio:
    identity: dict[str, Any]
    configs: tuple[dict[str, Any], ...]
    segments: tuple[dict[str, Any], ...]

    @property
    def settings(self) -> dict[str, Any]:
        result: dict[str, Any] = json.loads(self.configs[-1]["settings_json"])
        return result


def _rows(paths: list[Path]) -> list[dict[str, Any]]:
    return [row for path in paths for row in pq.read_table(path).to_pylist()]


class PortfolioBook:
    def __init__(self, store: ResultStore) -> None:
        self._store = store
        self._root = store.root / "portfolios"

    def _folder(self, name: str) -> Path:
        if not _NAME.fullmatch(name):
            raise DataError("portfolio names are letters, digits, - and _")
        return self._root / name

    def create(self, name: str, strategy: str, settings: dict[str, Any]) -> Portfolio:
        folder = self._folder(name)
        check_settings(strategy, settings)
        entry = strategy_entry(strategy)
        now = time.time_ns()
        identity = {
            "portfolio_id": [name],
            "strategy": [strategy],
            "family": [entry.family],
            "initial_capital": [Decimal(settings["capital"])],
            "created_at": [now],
        }
        (self._store.root / "staging").mkdir(exist_ok=True)
        staging = Path(tempfile.mkdtemp(dir=self._store.root / "staging"))
        try:
            write_new(staging / "portfolio.parquet", pa.table(identity, schema=PORTFOLIOS))
            self._add_config(staging, name, 1, settings, now)
            try:
                staging.rename(folder)
            except OSError:
                raise DataError(f"portfolio {name} already exists") from None
        finally:
            shutil.rmtree(staging, ignore_errors=True)
        return self.get(name)

    @staticmethod
    def _add_config(
        folder: Path, name: str, version: int, settings: dict[str, Any], now: int
    ) -> None:
        body = canonical(settings)
        row = {
            "portfolio_id": [name],
            "version": [version],
            "config_sha256": [digest(body)],
            "settings_json": [body.decode()],
            "created_at": [now],
        }
        write_new(
            folder / "configs" / f"{version:04d}.parquet", pa.table(row, schema=PORTFOLIO_CONFIGS)
        )

    def names(self) -> list[str]:
        return sorted(p.name for p in self._root.iterdir() if p.name != "_schema")

    def get(self, name: str) -> Portfolio:
        folder = self._folder(name)
        if not (folder / "portfolio.parquet").exists():
            raise DataError(f"no such portfolio: {name}")
        return Portfolio(
            _rows([folder / "portfolio.parquet"])[0],
            tuple(_rows(sorted((folder / "configs").glob("*.parquet")))),
            tuple(_rows(sorted((folder / "segments").glob("*.parquet")))),
        )

    def configure(self, name: str, overrides: list[tuple[list[str], Any]]) -> int:
        """A new settings version, effective from the next segment; history stays."""
        portfolio = self.get(name)
        strategy = portfolio.identity["strategy"]
        settings = apply_overrides(portfolio.settings, strategy, overrides)
        if settings == portfolio.settings:
            raise DataError("no setting changed")
        check_settings(strategy, settings)
        version = len(portfolio.configs) + 1
        try:
            self._add_config(self._folder(name), name, version, settings, time.time_ns())
        except FileExistsError:
            raise DataError("portfolio was reconfigured concurrently") from None
        return version

    def plan(
        self,
        name: str,
        source: MarketDataSource,
        *,
        start: str | None,
        end: str,
        allow_validation: bool = False,
        accept_code_change: bool = False,
        plugins: tuple[str, ...] = (),
    ) -> RunJob:
        """The next segment. A first segment needs `start`; a later one continues exactly where
        the last stopped, so a gap or an overlap cannot be requested at all."""
        portfolio = self.get(name)
        strategy = portfolio.identity["strategy"]
        head = portfolio.segments[-1] if portfolio.segments else None
        if head is None:
            if start is None:
                raise DataError("a portfolio's first segment needs a start date")
            first = start
            lineage_tail: dict[str, Any] = {
                "inception": start,
                "start_cash": portfolio.settings["capital"],
                "high_water": portfolio.settings["capital"],
                "trades_before": 0,
            }
        else:
            if start is not None:
                raise DataError("a continuation starts where the portfolio stopped; omit --start")
            if not head["continuable"]:
                raise DataError(f"portfolio {name} cannot continue: {head['stop_reason']}")
            if not strategy_entry(strategy).replayable:
                raise DataError("this strategy cannot be resumed: its state is not replayable")
            if head["code_sha256"] != code_version(plugins) and not accept_code_change:
                raise DataError(
                    "code changed since the last segment, so replay may not reproduce it; "
                    "pass --accept-code-change to continue and record that"
                )
            first = (date.fromisoformat(head["last_session"]) + timedelta(days=1)).isoformat()
            if end < first:
                raise DataError(f"portfolio {name} already covers {end}")
            lineage_tail = {
                "inception": portfolio.segments[0]["start_date"],
                "start_cash": str(head["end_cash"]),
                "high_water": str(head["high_water"]),
                "trades_before": head["trades_total"],
                "parent_run_id": head["run_id"],
                "history_sha256": head["history_sha256"],
            }
        interval = Interval(first, end)
        roles: tuple[str, ...] = ("synthetic",)
        if source.historical:
            roles = authorize(interval, allow_validation=allow_validation)
        lineage = Lineage(name, len(portfolio.segments) + 1, len(portfolio.configs), **lineage_tail)
        return RunJob(
            strategy,
            portfolio.settings,
            interval,
            source,
            self._store.root,
            roles,
            lineage,
            plugins,
        )

    def commit(self, job: RunJob, outcome: RunOutcome) -> None:
        """Append the segment. Creating its file is the atomic commit; a lost race changes
        nothing, and the published run simply stays unattached to the portfolio."""
        lineage = job.lineage
        checkpoint = outcome.checkpoint
        if lineage is None or checkpoint is None or outcome.status != "completed":
            raise DataError("only a completed portfolio run can be committed")
        name = lineage.portfolio_id
        head = self.get(name).segments
        if len(head) != lineage.segment - 1 or (
            head and head[-1]["run_id"] != lineage.parent_run_id
        ):
            raise DataError(f"portfolio {name} moved on while this segment ran")
        code = checkpoint["code_sha256"]
        row = {
            "portfolio_id": name,
            "segment": lineage.segment,
            "run_id": outcome.run_id,
            "parent_run_id": lineage.parent_run_id,
            "config_version": lineage.config_version,
            "start_date": job.interval.start,
            "end_date": job.interval.end,
            "last_session": checkpoint["last_session"],
            "start_cash": Decimal(lineage.start_cash),
            "end_cash": Decimal(checkpoint["cash"]),
            "high_water": Decimal(checkpoint["high_water"]),
            "trades_total": checkpoint["trades_total"],
            "continuable": not checkpoint["stop_reason"],
            "stop_reason": checkpoint["stop_reason"],
            "history_sha256": checkpoint["history_sha256"],
            "code_sha256": code,
            "code_changed": bool(head) and head[-1]["code_sha256"] != code,
            "committed_at": time.time_ns(),
        }
        path = self._folder(name) / "segments" / f"{lineage.segment:04d}.parquet"
        try:
            write_new(path, pa.Table.from_pylist([row], schema=SEGMENTS))
        except FileExistsError:
            raise DataError(f"portfolio {name} moved on while this segment ran") from None

    def report(self, name: str) -> dict[str, Any]:
        """A portfolio's whole life, with metrics recomputed across every segment."""
        portfolio = self.get(name)
        capital = portfolio.identity["initial_capital"]
        segments = portfolio.segments
        run_ids = [s["run_id"] for s in segments]
        manifests = [self._store.manifest(run_id) for run_id in run_ids]
        window = sum(m["data"]["window_ns"] for m in manifests)
        equity = self._store.table("equity", run_ids)
        last = equity.slice(equity.num_rows - 1).to_pydict() if equity.num_rows else None
        return {
            "portfolio_id": name,
            "strategy": portfolio.identity["strategy"],
            "family": portfolio.identity["family"],
            "initial_capital": str(capital),
            "cash": str(segments[-1]["end_cash"]) if segments else str(capital),
            "position": str(last["position"][0]) if last else "0",
            "equity": str(last["equity"][0]) if last else str(capital),
            "through": segments[-1]["last_session"] if segments else None,
            "continuable": segments[-1]["continuable"] if segments else True,
            "stop_reason": segments[-1]["stop_reason"] if segments else "",
            "config_versions": [
                {
                    "version": c["version"],
                    "config_sha256": c["config_sha256"],
                    "settings": json.loads(c["settings_json"]),
                }
                for c in portfolio.configs
            ],
            "segments": [
                {
                    "segment": s["segment"],
                    "run_id": s["run_id"],
                    "start": s["start_date"],
                    "end": s["end_date"],
                    "config_version": s["config_version"],
                    "start_cash": str(s["start_cash"]),
                    "end_cash": str(s["end_cash"]),
                    "code_changed": s["code_changed"],
                }
                for s in segments
            ],
            "metrics": compute(
                frame_of(self._store.table("trades", run_ids), equity, capital, window)
            ),
        }
