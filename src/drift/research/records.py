"""Maps one engine result to what is stored about it. Pure: no files, no engine.

`run_id` hashes every input that can change an outcome, so it names the experiment, not the
attempt; `results_sha256` hashes the outcomes without ids, so two runs can be compared by it.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import pyarrow as pa

from drift.backtest.config import BacktestConfig
from drift.backtest.registry import strategy_entry
from drift.backtest.report import BacktestResult
from drift.data.model import canonical, digest
from drift.research.metrics import compute, frame_of
from drift.research.scope import Interval
from drift.research.settings import cost_label
from drift.research.sources import Piece
from drift.research.store import RUN_TABLES, RunRecord
from drift.strategies.market import Candle


@dataclass(frozen=True, slots=True)
class Lineage:
    """A segment's place in a portfolio's history; independent experiments have none."""

    portfolio_id: str
    segment: int
    config_version: int
    inception: str  # the portfolio's first day: its agent replays everything from here
    start_cash: str
    high_water: str
    trades_before: int
    parent_run_id: str | None = None
    history_sha256: str | None = None


def history_digest(candles: tuple[Candle, ...]) -> str:
    """Identity of the exact candles an agent has seen, however they were partitioned."""
    return digest(
        canonical(
            [
                [c.start, c.available, str(c.open), str(c.high), str(c.low), str(c.close), c.volume]
                for c in candles
            ]
        )
    )


def _table(name: str, run_id: str, strategy: str, rows: list[tuple[Any, ...]]) -> pa.Table:
    schema = RUN_TABLES[name]
    columns = list(zip(*rows, strict=True)) if rows else [()] * (len(schema) - 2)
    arrays = {"run_id": [run_id] * len(rows), "strategy": [strategy] * len(rows)}
    return pa.table(arrays | dict(zip(schema.names[2:], map(list, columns), strict=True)), schema)


def _trades(key: str, result: BacktestResult, before: int) -> list[tuple[Any, ...]]:
    return [
        (
            digest(f"{key}|{t.proposal_id}|{t.entry_ts}".encode())[:24],
            before + t.number,
            t.side,
            t.quantity,
            t.entry_ts,
            t.exit_ts,
            t.held_seconds,
            t.entry_price,
            t.exit_price,
            t.gross_pnl,
            t.commission,
            t.net_pnl,
            t.exit_reason,
            t.signal,
            t.proposal_id,
            ";".join(t.flags),
        )
        for t in result.trades
    ]


def _equity(result: BacktestResult, high_water: Decimal) -> list[tuple[Any, ...]]:
    rows = []
    peak = high_water
    for ts, day, cash, position, mark, equity in result.ledger.equity:
        peak = max(peak, equity)
        gap = peak - equity
        rows.append((ts, day, cash, position, mark, equity, peak, gap, float(gap / peak)))
    return rows


def build_record(
    strategy: str,
    settings: dict[str, Any],
    interval: Interval,
    roles: tuple[str, ...],
    lineage: Lineage | None,
    config: BacktestConfig,
    piece: Piece,
    result: BacktestResult,
    code: str,
    plugins: dict[str, str],
) -> RunRecord:
    summary = result.data_summary
    place = None
    if lineage is not None:
        place = [lineage.portfolio_id, lineage.segment, lineage.config_version]
    identity = {
        "kind": "portfolio" if lineage else "experiment",
        "strategy": strategy,
        "interval": [interval.start, interval.end],
        "place": place,
        "parent": lineage.parent_run_id if lineage else None,
        "config": result.config_sha256,
        "data": result.data_sha256,
        "code": code,
    }
    run_id = digest(canonical(identity))[:24]
    ledger = result.ledger
    before = lineage.trades_before if lineage else 0
    high_water = Decimal(lineage.high_water) if lineage else config.capital
    tables = {
        "trades": _table(
            "trades",
            run_id,
            strategy,
            _trades(lineage.portfolio_id if lineage else run_id, result, before),
        ),
        "orders": _table(
            "orders",
            run_id,
            strategy,
            [
                (
                    o["order"],
                    o["ts"],
                    o["kind"],
                    o["side"],
                    o["quantity"],
                    o["reason"],
                    o["proposal_id"],
                    o["status"],
                )
                for o in ledger.orders
            ],
        ),
        "fills": _table(
            "fills",
            run_id,
            strategy,
            [
                (f["order"], f["ts"], f["side"], f["quantity"], f["price"], f["commission"])
                for f in ledger.fills
            ],
        ),
        "equity": _table("equity", run_id, strategy, _equity(result, high_water)),
        "proposals": _table(
            "proposals",
            run_id,
            strategy,
            [
                (
                    p["proposal_id"],
                    p["generated_at"],
                    p["intent"],
                    p["status"],
                    p["rationale"],
                    ";".join(p["reasons"]),
                )
                for p in result.proposals
            ],
        ),
    }
    equity = tables["equity"]
    frame = frame_of(tables["trades"], equity, config.capital, summary["window_ns"])
    measured = compute(frame)
    tables["metrics"] = _table(
        "metrics",
        run_id,
        strategy,
        [(name, value) for name, value in measured.items() if value is not None],
    )
    outcomes = pa.BufferOutputStream()
    for name in sorted(tables):
        table = tables[name].drop_columns(
            [c for c in ("run_id", "trade_id") if c in tables[name].column_names]
        )
        with pa.ipc.new_stream(outcomes, table.schema) as stream:
            stream.write_table(table)
    results_sha256 = digest(outcomes.getvalue().to_pybytes())
    end_cash = result.reconciliation["engine_balance"]
    missing = sum(count for day, count in piece.gaps if day >= interval.start)
    entry = strategy_entry(strategy)
    stop_reason = (
        "open position at the end of data"
        if result.open_at_end
        else "an order may be live across the session boundary"
        if ledger.carried_order
        else ""
    )
    manifest: dict[str, Any] = {
        "version": 1,
        "run_id": run_id,
        "kind": identity["kind"],
        "strategy": strategy,
        "family": entry.family,
        "interval": {"start": interval.start, "end": interval.end},
        "research_role": "+".join(roles),
        "synthetic": summary["source_ref"] is None,
        "portfolio": lineage
        and {
            "id": lineage.portfolio_id,
            "segment": lineage.segment,
            "config_version": lineage.config_version,
            "parent_run_id": lineage.parent_run_id,
        },
        "cost_profile": cost_label(settings["execution"]),
        "settings": settings,
        "config": result.config,
        "config_sha256": result.config_sha256,
        "data_sha256": result.data_sha256,
        "data": summary | {"missing_minutes": missing},
        "software": result.software,
        "plugins": plugins,
        "code_sha256": code,
        "results_sha256": results_sha256,
        "reconciliation": result.reconciliation,
        "rejections": len(result.rejections),
        "open_at_end": result.open_at_end,
        "metrics": measured,
        "checkpoint": {
            "cash": end_cash,
            "high_water": str(equity.column("high_water")[-1].as_py()),
            "last_session": ledger.equity[-1][1],
            "trades_total": before + len(result.trades),
            "stop_reason": stop_reason,
            "history_sha256": history_digest(piece.data.candles),
            "code_sha256": code,
        },
    }
    row = {
        "run_id": run_id,
        "strategy": strategy,
        "kind": manifest["kind"],
        "family": entry.family,
        "start_date": interval.start,
        "end_date": interval.end,
        "research_role": manifest["research_role"],
        "synthetic": manifest["synthetic"],
        "portfolio_id": lineage.portfolio_id if lineage else None,
        "segment": lineage.segment if lineage else None,
        "config_version": lineage.config_version if lineage else None,
        "parent_run_id": lineage.parent_run_id if lineage else None,
        "cost_profile": manifest["cost_profile"],
        "capital": config.capital,
        "config_sha256": result.config_sha256,
        "data_sha256": result.data_sha256,
        "source_ref": summary["source_ref"],
        "feed": summary["feed"],
        "code_sha256": code,
        "results_sha256": results_sha256,
        "sessions": summary["sessions"],
        "candles": summary["candles"],
        "replayed_candles": summary["replayed_candles"],
        "missing_minutes": missing,
        "rejections": len(result.rejections),
        "open_at_end": result.open_at_end is not None,
        "config_json": canonical(result.config).decode(),
    }
    tables["run"] = pa.Table.from_pylist([row], schema=RUN_TABLES["run"])
    return RunRecord(run_id, manifest, tables)
