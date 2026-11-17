"""Durable research results: immutable Parquet files, read through DuckDB views.

Nothing here is a database to keep in sync. Each run is one directory, published atomically
and never rewritten; its id is derived from its inputs, so repeating a run cannot duplicate it
and any disagreement in the results is an error, not a new version. Any DuckDB client can read
the same Parquet globs, which is the seam a dashboard will use; `connect` names them as views.
"""

import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from drift.data.model import DataError, canonical, digest
from drift.research.metrics import metric_names

_IDENTIFIER = re.compile(r"[a-z][a-z0-9_]*")
MONEY = pa.decimal128(26, 6)
TIME = pa.timestamp("ns", tz="UTC")
_S, _I, _F, _B = pa.string(), pa.int64(), pa.float64(), pa.bool_()
_KEY = [("run_id", _S), ("strategy", _S)]

RUN_TABLES: dict[str, pa.Schema] = {
    "run": pa.schema(
        [
            *_KEY,
            ("kind", _S),
            ("family", _S),
            ("start_date", _S),
            ("end_date", _S),
            ("research_role", _S),
            ("synthetic", _B),
            ("portfolio_id", _S),
            ("segment", _I),
            ("config_version", _I),
            ("parent_run_id", _S),
            ("cost_profile", _S),
            ("capital", MONEY),
            ("config_sha256", _S),
            ("data_sha256", _S),
            ("source_ref", _S),
            ("feed", _S),
            ("code_sha256", _S),
            ("results_sha256", _S),
            ("sessions", _I),
            ("candles", _I),
            ("replayed_candles", _I),
            ("missing_minutes", _I),
            ("rejections", _I),
            ("open_at_end", _B),
            ("config_json", _S),
        ]
    ),
    "trades": pa.schema(
        [
            *_KEY,
            ("trade_id", _S),
            ("number", _I),
            ("side", _S),
            ("quantity", MONEY),
            ("entry_ts", TIME),
            ("exit_ts", TIME),
            ("held_seconds", _I),
            ("entry_price", MONEY),
            ("exit_price", MONEY),
            ("gross_pnl", MONEY),
            ("commission", MONEY),
            ("net_pnl", MONEY),
            ("exit_reason", _S),
            ("signal", _S),
            ("proposal_id", _S),
            ("flags", _S),
        ]
    ),
    "orders": pa.schema(
        [
            *_KEY,
            ("order_number", _I),
            ("submitted_ts", TIME),
            ("kind", _S),
            ("side", _S),
            ("quantity", MONEY),
            ("reason", _S),
            ("proposal_id", _S),
            ("status", _S),
        ]
    ),
    "fills": pa.schema(
        [
            *_KEY,
            ("order_number", _I),
            ("ts", TIME),
            ("side", _S),
            ("quantity", MONEY),
            ("price", MONEY),
            ("commission", MONEY),
        ]
    ),
    "equity": pa.schema(
        [
            *_KEY,
            ("ts", TIME),
            ("session_date", _S),
            ("cash", MONEY),
            ("position", MONEY),
            ("mark", MONEY),
            ("equity", MONEY),
            ("high_water", MONEY),
            ("drawdown", MONEY),
            ("drawdown_pct", _F),
        ]
    ),
    "proposals": pa.schema(
        [
            *_KEY,
            ("proposal_id", _S),
            ("generated_ts", TIME),
            ("intent", _S),
            ("status", _S),
            ("rationale", _S),
            ("reasons", _S),
        ]
    ),
    "metrics": pa.schema([*_KEY, ("metric", _S), ("value", _F)]),
}
BATCHES = pa.schema(
    [
        ("batch_id", _S),
        ("label", _S),
        ("position", _I),
        ("strategy", _S),
        ("portfolio_id", _S),
        ("run_id", _S),
        ("status", _S),
        ("reused", _B),
        ("error_type", _S),
        ("error", _S),
        ("traceback", _S),
        ("seconds", _F),
        ("workers", _I),
        ("started_at", TIME),
    ]
)
PORTFOLIOS = pa.schema(
    [
        ("portfolio_id", _S),
        ("strategy", _S),
        ("family", _S),
        ("initial_capital", MONEY),
        ("created_at", TIME),
    ]
)
PORTFOLIO_CONFIGS = pa.schema(
    [
        ("portfolio_id", _S),
        ("version", _I),
        ("config_sha256", _S),
        ("settings_json", _S),
        ("created_at", TIME),
    ]
)
SEGMENTS = pa.schema(
    [
        ("portfolio_id", _S),
        ("segment", _I),
        ("run_id", _S),
        ("parent_run_id", _S),
        ("config_version", _I),
        ("start_date", _S),
        ("end_date", _S),
        ("last_session", _S),
        ("start_cash", MONEY),
        ("end_cash", MONEY),
        ("high_water", MONEY),
        ("trades_total", _I),
        ("continuable", _B),
        ("stop_reason", _S),
        ("history_sha256", _S),
        ("code_sha256", _S),
        ("code_changed", _B),
        ("committed_at", TIME),
    ]
)
_FILES: dict[str, tuple[str, pa.Schema]] = {
    **{
        ("runs" if name == "run" else name): (f"runs/*/{name}.parquet", schema)
        for name, schema in RUN_TABLES.items()
    },
    "batches": ("batches/*.parquet", BATCHES),
    "portfolios": ("portfolios/*/portfolio.parquet", PORTFOLIOS),
    "portfolio_configs": ("portfolios/*/configs/*.parquet", PORTFOLIO_CONFIGS),
    "portfolio_segments": ("portfolios/*/segments/*.parquet", SEGMENTS),
}
_DERIVED = (
    """CREATE VIEW portfolio_trades AS SELECT s.portfolio_id, s.segment, t.*
       FROM trades t JOIN portfolio_segments s USING (run_id)""",
    """CREATE VIEW portfolio_equity AS SELECT s.portfolio_id, s.segment, e.*
       FROM equity e JOIN portfolio_segments s USING (run_id)""",
)


@dataclass(frozen=True, slots=True)
class RunRecord:
    run_id: str
    manifest: dict[str, Any]
    tables: dict[str, pa.Table]


def _written(path: Path, table: pa.Table) -> Path:
    """`table` durably on disk beside `path`, ready to be moved into place."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.stem}.{os.getpid()}.tmp")
    pq.write_table(table, temporary, compression="zstd")
    with temporary.open("rb") as stream:
        os.fsync(stream.fileno())
    return temporary


def write_new(path: Path, table: pa.Table) -> None:
    """Create `path` with `table`, or raise FileExistsError: the commit point of an append."""
    temporary = _written(path, table)
    try:
        os.link(temporary, path)
    finally:
        temporary.unlink()


class ResultStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        for pattern, schema in _FILES.values():
            # An empty typed file per glob: views exist and keep their types in an empty store.
            placeholder = root / pattern.replace("*", "_schema", 1).replace("*", "0")
            if not placeholder.exists():
                try:
                    write_new(placeholder, schema.empty_table())
                except FileExistsError:
                    pass

    def _run_dir(self, run_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{24}", run_id):
            raise DataError("invalid run id")
        return self.root / "runs" / run_id

    def publish(self, record: RunRecord) -> bool:
        """Atomically add a run; False when an identical run already exists."""
        final = self._run_dir(record.run_id)
        if final.exists():
            self._confirm(record)
            return False
        (self.root / "staging").mkdir(exist_ok=True)
        staging = Path(tempfile.mkdtemp(dir=self.root / "staging"))
        try:
            for name, table in record.tables.items():
                pq.write_table(table, staging / f"{name}.parquet", compression="zstd")
            inventory = {
                p.name: digest(p.read_bytes()) for p in sorted(staging.iterdir()) if p.is_file()
            }
            body = canonical(record.manifest | {"inventory": inventory})
            (staging / "manifest.json").write_bytes(body)
            (staging / "COMPLETE").write_text(digest(body))
            for path in staging.iterdir():
                with path.open("rb") as stream:
                    os.fsync(stream.fileno())
            try:
                staging.rename(final)
            except OSError:
                if not final.exists():
                    raise
                self._confirm(record)  # lost a race against the same run
                return False
            return True
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    def _confirm(self, record: RunRecord) -> None:
        if self.manifest(record.run_id)["results_sha256"] != record.manifest["results_sha256"]:
            raise DataError("same inputs produced different results: run is not reproducible")

    def manifest(self, run_id: str) -> dict[str, Any]:
        folder = self._run_dir(run_id)
        try:
            body = (folder / "manifest.json").read_bytes()
            if (folder / "COMPLETE").read_text() != digest(body):
                raise DataError("run manifest does not match its commit marker")
        except FileNotFoundError:
            raise DataError(f"no such run: {run_id}") from None
        result: dict[str, Any] = json.loads(body)
        return result

    def table(self, name: str, run_ids: list[str]) -> pa.Table:
        """One table across runs, in the given order, with its files hash-checked."""
        tables = [RUN_TABLES[name].empty_table()]
        for run_id in run_ids:
            path = self._run_dir(run_id) / f"{name}.parquet"
            body = path.read_bytes()
            if digest(body) != self.manifest(run_id)["inventory"][path.name]:
                raise DataError("stored table differs from its manifest")
            tables.append(pq.read_table(pa.BufferReader(body)))
        return pa.concat_tables(tables, promote_options="default")

    def record_batch(self, batch_id: str, rows: dict[str, list[Any]]) -> None:
        """Every attempt, failed ones included: the trial log behind the results. A batch
        rewrites its own row set as it progresses; nothing else in the store changes in place."""
        path = self.root / "batches" / f"{batch_id}.parquet"
        os.replace(_written(path, pa.table(rows, schema=BATCHES)), path)

    def connect(self) -> Any:
        """Read-only views: runs, trades, orders, fills, equity, proposals, metrics, comparison,
        batches, portfolios, portfolio_configs, portfolio_segments, portfolio_trades and
        portfolio_equity."""
        db = duckdb.connect(
            config={
                "threads": 2,
                "memory_limit": "1GB",
                "autoinstall_known_extensions": False,
                "autoload_known_extensions": False,
            }
        )
        for view, (pattern, _) in _FILES.items():
            db.read_parquet(
                str(self.root / pattern), hive_partitioning=False, union_by_name=True
            ).create_view(view)
        for statement in _DERIVED:
            db.execute(statement)
        stored = [row[0] for row in db.execute("SELECT DISTINCT metric FROM metrics").fetchall()]
        names = dict.fromkeys((*metric_names(), *stored))
        columns = ", ".join(
            f"max(value) FILTER (metric = '{name}') AS {name}"
            for name in names
            if _IDENTIFIER.fullmatch(name)  # read from files, so never trusted as SQL
        )
        db.execute(
            f"""CREATE VIEW comparison AS
                SELECT r.run_id, r.strategy, r.family, r.kind, r.portfolio_id, r.segment,
                       r.start_date, r.end_date, r.research_role, r.cost_profile, r.capital,
                       m.* EXCLUDE (run_id)
                FROM runs r JOIN (SELECT run_id, {columns} FROM metrics GROUP BY run_id) m
                USING (run_id)"""
        )
        return db
