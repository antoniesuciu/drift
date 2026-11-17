"""Runs strategy jobs. A job holds everything a fresh process needs and no shared state.

`execute` is the only code that touches the engine and the store, always in this order: load,
check, simulate, publish. `attempt` turns any failure into a recorded outcome, which is what
isolates strategies from each other. `run_batch` depends only on an `Executor`, so sequential
and concurrent runs share every line that can affect a result.
"""

import time
import traceback
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from drift.backtest.engine import run_on, software
from drift.backtest.registry import load_plugins, plugin_digests, strategy_entry
from drift.data.model import DataError, canonical, digest
from drift.research.records import Lineage, build_record, history_digest
from drift.research.scope import Interval
from drift.research.settings import backtest_config
from drift.research.sources import MarketDataSource
from drift.research.store import ResultStore


@dataclass(frozen=True, slots=True)
class RunJob:
    strategy: str
    settings: dict[str, Any]
    interval: Interval  # the window that trades
    source: MarketDataSource
    store: Path
    roles: tuple[str, ...]  # research roles already authorized for this window
    lineage: Lineage | None = None
    plugins: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RunOutcome:
    strategy: str
    status: str  # "completed" | "failed" | "started", which a finished batch never leaves
    seconds: float
    portfolio_id: str | None = None
    run_id: str | None = None
    reused: bool = False
    error_type: str | None = None
    error: str | None = None
    traceback: str | None = None
    checkpoint: dict[str, Any] | None = None


def code_version(plugins: Sequence[str]) -> str:
    """Everything executable behind a result: package source, engine, Python and plugins."""
    return digest(canonical([software(), plugin_digests(plugins)]))


def _portfolio(job: RunJob) -> str | None:
    return job.lineage.portfolio_id if job.lineage else None


def failed(job: RunJob, kind: str, message: str, seconds: float, trace: str = "") -> RunOutcome:
    return RunOutcome(
        job.strategy, "failed", seconds, _portfolio(job), None, False, kind, message, trace
    )


def execute(job: RunJob) -> RunOutcome:
    started = time.monotonic()
    load_plugins(job.plugins)
    entry = strategy_entry(job.strategy)
    lineage = job.lineage
    capital = lineage.start_cash if lineage else job.settings["capital"]
    window = Interval(lineage.inception, job.interval.end) if lineage else job.interval
    piece = job.source.load(window)
    candles = piece.data.candles
    prior = tuple(c for c in candles if c.day < job.interval.start)
    if len(prior) == len(candles):
        raise DataError("no sessions in the requested interval")
    if lineage is not None and lineage.parent_run_id is not None:
        if not entry.replayable:
            raise DataError("this strategy cannot be resumed: its state is not replayable")
        if history_digest(prior) != lineage.history_sha256:
            raise DataError("market history changed since the last segment: refusing to resume")
    name = f"{job.strategy}-{job.interval.start}-{job.interval.end}"
    config = backtest_config(job.strategy, job.settings, piece, name=name, capital=capital)
    if piece.splits:
        if config.strategy.exit.flatten_lead_seconds is None:
            raise DataError("a position could cross a split: raw units would misstate its PnL")
        if not entry.split_safe(config.strategy.params):
            raise DataError(
                "this configuration compares raw prices or volumes across a split, so it is "
                "not split-neutral; choose a window without one"
            )
    result = run_on(config, piece.data, trade_from=candles[len(prior)].start, evaluate=job.roles)
    if not result.reconciliation["ok"]:
        raise DataError("engine and ledger balances do not reconcile")
    record = build_record(
        job.strategy,
        job.settings,
        job.interval,
        job.roles,
        lineage,
        config,
        piece,
        result,
        code_version(job.plugins),
        plugin_digests(job.plugins),
    )
    created = ResultStore(job.store).publish(record)
    return RunOutcome(
        job.strategy,
        "completed",
        time.monotonic() - started,
        lineage.portfolio_id if lineage else None,
        record.run_id,
        not created,
        checkpoint=record.manifest["checkpoint"],
    )


def attempt(job: RunJob) -> RunOutcome:
    """`execute`, with every failure contained in its outcome."""
    started = time.monotonic()
    try:
        return execute(job)
    except Exception as exc:
        seconds = time.monotonic() - started
        return failed(job, type(exc).__name__, str(exc)[:500], seconds, traceback.format_exc())


class Executor(Protocol):
    @property
    def workers(self) -> int: ...

    def run(self, jobs: Sequence[RunJob], report: Callable[[int, RunOutcome], None]) -> None:
        """Report one outcome per job index as it ends; never raises for a job's failure."""


@dataclass(frozen=True, slots=True)
class Batch:
    batch_id: str
    outcomes: tuple[RunOutcome, ...]

    @property
    def ok(self) -> bool:
        return all(o.status == "completed" for o in self.outcomes)


def run_batch(
    jobs: Sequence[RunJob], executor: Executor, store: ResultStore, *, label: str
) -> Batch:
    """Run `jobs`, keeping the trial log true however it ends: attempts are on record before
    anything runs, so a killed process leaves `started` rows, and an interrupted batch still
    logs every outcome it reached."""
    batch_id = uuid4().hex[:24]
    started = time.time_ns()
    outcomes: dict[int, RunOutcome] = {}

    def log() -> None:
        rows = [
            outcomes.get(i, RunOutcome(job.strategy, "started", 0.0, _portfolio(job)))
            for i, job in enumerate(jobs)
        ]
        count = len(rows)
        store.record_batch(
            batch_id,
            {
                "batch_id": [batch_id] * count,
                "label": [label] * count,
                "position": list(range(count)),
                "strategy": [o.strategy for o in rows],
                "portfolio_id": [o.portfolio_id for o in rows],
                "run_id": [o.run_id for o in rows],
                "status": [o.status for o in rows],
                "reused": [o.reused for o in rows],
                "error_type": [o.error_type for o in rows],
                "error": [o.error for o in rows],
                "traceback": [o.traceback for o in rows],
                "seconds": [o.seconds for o in rows],
                "workers": [executor.workers] * count,
                "started_at": [started] * count,
            },
        )

    log()
    try:
        executor.run(jobs, outcomes.__setitem__)
    finally:
        log()
    return Batch(batch_id, tuple(outcomes[i] for i in range(len(jobs))))
