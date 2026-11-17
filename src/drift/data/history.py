"""Small resumable monthly development archive, local DuckDB and fixed baseline reports."""

import argparse
import calendar as month_calendar
import json
import re
import shutil
import time
from collections.abc import Collection
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import duckdb

from drift.backtest.config import STRATEGIES, BacktestConfig, default_config
from drift.backtest.data import MarketData
from drift.backtest.data import research_role as role
from drift.backtest.engine import run_on
from drift.data.alpaca import AlpacaClient, Credentials
from drift.data.equity import PilotRequest
from drift.data.equity_store import acquire, load
from drift.data.model import DataError, canonical, digest
from drift.data.store import publication_lock, safe_file
from drift.strategies.calendar import Calendar


def storage_bytes(root: Path) -> int:
    return sum(p.stat().st_size for p in root.rglob("*") if p.is_file())


class StorageLimit(DataError):
    """Intentional download stop; completed partitions remain usable."""


def check_storage(root: Path, limit: int, min_free: int, reserve: int = 0) -> None:
    if storage_bytes(root) + reserve > limit or shutil.disk_usage(root).free - reserve < min_free:
        raise StorageLimit("archive size/free-space budget reached")


def months(start: str, end: str) -> list[str]:
    try:
        if any(not re.fullmatch(r"202[0-5]-(0[1-9]|1[0-2])", v) for v in (start, end)):
            raise ValueError
        a, b = time.strptime(start, "%Y-%m"), time.strptime(end, "%Y-%m")
        if not 2020 <= a.tm_year <= b.tm_year <= 2025 or start > end:
            raise ValueError
        return [
            f"{y:04d}-{m:02d}"
            for y in range(a.tm_year, b.tm_year + 1)
            for m in range(1, 13)
            if start <= f"{y:04d}-{m:02d}" <= end
        ]
    except (ValueError, TypeError):
        raise DataError("months must be YYYY-MM within the authorized 2020–2025 archive") from None


def _save(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_bytes(canonical(value))
    temp.replace(path)


def partitions(
    root: Path, *, research_role: str | None = None, selected: Collection[str] | None = None
) -> list[Path]:
    """Fully verified partitions. `selected` months limit verification to what a task reads."""
    index = json.loads((root / "index.json").read_bytes())
    rows = index["months"]
    names = [r["month"] for r in rows]
    if not names or names != sorted(set(names)) or any(months(m, m) != [m] for m in names):
        raise DataError("invalid development partition index")
    if selected is not None:
        rows = [r for r in rows if r["month"] in selected]
    paths = [safe_file(root, r["dataset"] + "/manifest.json").parent for r in rows]
    for record, path in zip(rows, paths, strict=True):
        data, manifest = load(path)
        quality = json.loads((path / "quality.json").read_bytes())
        if (
            manifest["dataset_id"] != record["dataset_id"]
            or manifest["request"]["feed"] != "sip"
            or manifest["request"]["start"][:7] != record["month"]
            or manifest["request"]["end"][:7] != record["month"]
            or record["bars"] != len(data.candles)
            or record["missing_minutes"]
            != sum(len(s["missing_starts"]) for s in quality["sessions"])
        ):
            raise DataError("partition identity/feed/month differs from index")
    return [
        p
        for r, p in zip(rows, paths, strict=True)
        if research_role is None or role(r["month"]) == research_role
    ]


def fetch(
    root: Path,
    credentials: Credentials,
    start: str,
    end: str,
    *,
    max_bytes: int = 2 * 1024**3,
    min_free_bytes: int = 5 * 1024**3,
) -> dict[str, Any]:
    selected = months(start, end)
    root.mkdir(parents=True, exist_ok=True)
    with publication_lock(root, "nvda-history"):
        index: dict[str, Any] = (
            json.loads((root / "index.json").read_bytes())
            if (root / "index.json").exists()
            else {
                "version": 1,
                "symbol": "NVDA",
                "feed": "sip",
                "adjustment": "raw",
                "months": [],
            }
        )
        existing = {r["month"]: r for r in index["months"]}
        index.update(max_bytes=max_bytes, min_free_bytes=min_free_bytes, requested_end=end)
        if existing:
            partitions(root)
        for month in selected:
            if month in existing:
                print(json.dumps({"month": month, "cached": True}), flush=True)
                continue
            y, m = map(int, month.split("-"))
            request = PilotRequest(
                f"{month}-01", f"{month}-{month_calendar.monthrange(y, m)[1]}", page_size=10000
            )
            output = root / f"year={y}" / f"month={m:02d}"
            started = time.monotonic()
            client = AlpacaClient(credentials)
            try:

                def budget(reserve: int) -> None:
                    check_storage(root, max_bytes, min_free_bytes, reserve)

                budget(64 * 1024**2)
                path = acquire(request, client, output, check_storage=budget)
            except StorageLimit:
                index["stop_reason"] = "storage_budget"
                _save(root / "index.json", index)
                return index
            except DataError:
                _save(
                    root / "last-failure.json",
                    {
                        "month": month,
                        "requests": len(client.requests),
                        "state": "incomplete; successful session receipts retained",
                    },
                )
                raise
            data, manifest = load(path)
            quality = json.loads((path / "quality.json").read_bytes())
            record = {
                "month": month,
                "research_role": role(month),
                "dataset": str(path.relative_to(root)),
                "dataset_id": manifest["dataset_id"],
                "bars": len(data.candles),
                "sessions": len(data.calendar.sessions),
                "missing_minutes": sum(len(s["missing_starts"]) for s in quality["sessions"]),
                "elapsed_seconds": time.monotonic() - started,
                "requests": len(client.requests),
            }
            existing[month] = record
            index["months"] = [existing[m] for m in sorted(existing)]
            _save(root / "index.json", index)
            print(json.dumps(record), flush=True)
            time.sleep(
                3
            )  # Deliberately sequential; per-request quota/backoff stays in the adapter.
        return index


def connect(root: Path, *, research_role: str | None = "development") -> Any:
    """Local SQL view over verified Parquet, two threads, 512 MiB, no extension downloads."""
    paths = partitions(root, research_role=research_role)
    if not paths:
        raise DataError("no verified partitions for the requested research role")
    files = [str(p / "bars.parquet") for p in paths]
    if not all(Path(p).is_file() for p in files):
        raise DataError("analytical Parquet missing; resume publication before SQL analysis")
    db = duckdb.connect(
        config={
            "threads": 2,
            "memory_limit": "512MB",
            "autoinstall_known_extensions": False,
            "autoload_known_extensions": False,
        }
    )
    db.read_parquet(files, hive_partitioning=False, union_by_name=True).create_view("bars")
    return db


def inspect(root: Path) -> dict[str, Any]:
    with connect(
        root, research_role=None
    ) as db:  # Mechanical integrity only, no strategy evaluation.
        rows, unique, days, first, last = db.execute(
            "SELECT count(*), count(DISTINCT start_ns), count(DISTINCT session_date), "
            "min(session_date), max(session_date) FROM bars"
        ).fetchone()
        invalid = db.execute(
            "SELECT count(*) FROM bars WHERE low <= 0 OR low > least(open,close) "
            "OR high < greatest(open,close) OR volume < 0 OR end_ns-start_ns != 60000000000 "
            "OR available_ns < end_ns OR feed != 'sip'"
        ).fetchone()[0]
    if rows != unique or invalid:
        raise DataError("DuckDB found duplicate/invalid historical rows")
    index = json.loads((root / "index.json").read_bytes())
    return {
        "feed": "sip",
        "adjustment": "raw",
        "months": len(index["months"]),
        "bars": rows,
        "sessions": days,
        "first": first,
        "last": last,
        "missing_minutes": sum(r["missing_minutes"] for r in index["months"]),
        "duplicates": rows - unique,
        "invalid_rows": invalid,
        "duckdb": duckdb.__version__,
    }


def combined(root: Path) -> tuple[MarketData, list[dict[str, Any]]]:
    data: list[MarketData] = []
    splits: dict[str, dict[str, Any]] = {}
    ids: list[str] = []
    for path in partitions(root, research_role="development"):
        part, manifest = load(path)
        data.append(part)
        ids.append(manifest["dataset_id"])
        for split in manifest["splits"]:
            if split["day"] in splits and splits[split["day"]] != split:
                raise DataError("conflicting split evidence")
            splits[split["day"]] = split
    base = replace(data[0].instrument, data_precision=None)
    if any(replace(p.instrument, data_precision=None) != base for p in data):
        raise DataError("incompatible monthly instruments")
    instrument = replace(base, data_precision=max(p.instrument.precision for p in data))
    # Missing months/sessions cannot become an apparently consecutive prior-close input.
    names = [p.calendar.sessions[0].day[:7] for p in data]
    if names != months(names[0], names[-1]):
        raise DataError("backtests require contiguous acquired months")
    result = MarketData.build(
        instrument,
        Calendar(tuple(s for p in data for s in p.calendar.sessions)),
        tuple(c for p in data for c in p.candles),
        source_ref=digest(canonical(ids)),
        source_feed="sip",
    )
    return result, [splits[d] for d in sorted(splits)]


def baselines(root: Path, output: Path) -> dict[str, Any]:
    """One frozen untuned long-only configuration per strategy, costs declared before runs."""
    quality = inspect(root)
    data, splits = combined(root)
    configs = {}
    for strategy in STRATEGIES:
        raw = default_config(strategy)
        raw.update(
            version=2,
            synthetic=False,
            name=f"nvda-{strategy}-development",
            instrument=asdict(data.instrument) | {"tick": str(data.instrument.tick)},
            data={"dataset_id": data.source_ref},
            capital="10000",
        )
        raw["sizing"] = {"mode": "fixed_quantity", "amount": "1"}
        raw["risk"].update(max_quantity="1", max_notional="1000", max_leverage="1")
        raw["execution"]["slippage_ticks"] = 1
        raw["strategy"]["params"]["allow_short"] = False
        if strategy == "itsm":
            raw["strategy"]["params"]["splits"] = [[s["day"], s["ratio"]] for s in splits]
        configs[strategy] = BacktestConfig.parse(raw)
    output = output / ("baseline-" + str(data.source_ref)[:16])
    output.mkdir(parents=True, exist_ok=True)
    protocol = {
        "version": 1,
        "data_quality": quality,
        "configs": {k: c.payload() for k, c in configs.items()},
        "notice": (
            "Untuned development baselines, not OOS or paper promotion. One raw share, long-only. "
            "Illustrative dated IBKR-reference commission/minimum/regulatory inputs, not an "
            "era-specific fee certification or Alpaca-paper fee model. One tick half-spread plus "
            "one adverse slippage tick each side; modeled bar-open fills, realized drawdown only. "
            "First session lacks prior-close context outside the acquired range; "
            "missing inputs abstain."
        ),
    }
    if (output / "protocol.json").exists() and json.loads(
        (output / "protocol.json").read_bytes()
    ) != protocol:
        raise DataError("baseline protocol differs; use a new output directory for a new trial")
    _save(output / "protocol.json", protocol)  # Persist all configs before viewing any result.
    reports = {}
    for name, config in configs.items():
        with (output / "trials.jsonl").open("a") as log:
            log.write(
                json.dumps({"strategy": name, "state": "started", "at_ns": time.time_ns()}) + "\n"
            )
        try:
            result = run_on(config, data)
            result.write(output / name)
            if not result.reconciliation["ok"] or result.open_at_end is not None:
                raise DataError("baseline has unresolved engine/ledger state")
        except Exception as exc:
            with (output / "trials.jsonl").open("a") as log:
                log.write(
                    json.dumps(
                        {"strategy": name, "state": "failed", "error_type": type(exc).__name__}
                    )
                    + "\n"
                )
            raise
        with (output / "trials.jsonl").open("a") as log:
            log.write(
                json.dumps(
                    {
                        "strategy": name,
                        "state": "completed",
                        "results_sha256": result.results_sha256,
                    }
                )
                + "\n"
            )
        reports[name] = {"metrics": result.metrics, "results_sha256": result.results_sha256}
        _save(output / "summary.json", {"protocol": protocol, "reports": reports})
        print(
            json.dumps(
                {
                    "strategy": name,
                    "trades": result.metrics["trades"],
                    "net_pnl": result.metrics["net_pnl"],
                    "max_drawdown": result.metrics["max_drawdown"],
                    "results_sha256": result.results_sha256,
                }
            ),
            flush=True,
        )
    return {"output": str(output), "reports": reports}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("fetch", "check", "baselines"))
    parser.add_argument("--root", type=Path, default=Path("data/nvda-history"))
    parser.add_argument("--start-month", default="2020-01")
    parser.add_argument("--end-month", default="2020-01")
    parser.add_argument("--credentials-file", type=Path)
    parser.add_argument("--authorize-historical", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("outputs/nvda-history"))
    parser.add_argument("--max-gib", type=int, default=2)
    parser.add_argument("--min-free-gib", type=int, default=5)
    parser.add_argument(
        "--store-only", action="store_true", help="authorize later-year storage only"
    )
    args = parser.parse_args()
    try:
        if args.command == "fetch":
            if not args.authorize_historical or args.credentials_file is None:
                parser.error("fetch requires explicit credentials and --authorize-historical")
            if args.end_month > "2022-12" and not args.store_only:
                parser.error(
                    "2023–2025 acquisition requires --store-only; strategy evaluation disabled"
                )
            if not 1 <= args.max_gib <= 5 or args.min_free_gib < 5:
                parser.error("storage budget must be 1–5 GiB and preserve at least 5 GiB free")
            fetch(
                args.root,
                Credentials.read(args.credentials_file),
                args.start_month,
                args.end_month,
                max_bytes=args.max_gib * 1024**3,
                min_free_bytes=args.min_free_gib * 1024**3,
            )
            report = inspect(args.root)
        elif args.command == "check":
            report = inspect(args.root)
        else:
            result = baselines(args.root, args.output)
            report = {"output": result["output"], "strategies": len(result["reports"])}
        print(json.dumps(report), flush=True)
    except DataError as exc:
        parser.exit(2, f"Historical operation stopped: {exc}; completed data retained.\n")
    except (OSError, ValueError, TypeError, KeyError):
        parser.exit(2, "Historical operation stopped; completed monthly data/receipts retained.\n")


if __name__ == "__main__":
    main()
