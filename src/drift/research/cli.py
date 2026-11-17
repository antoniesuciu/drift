"""`drift research ...` and `drift portfolio ...`: the framework's command line."""

import argparse
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from drift.backtest.data import InstrumentSpec, SyntheticSpec
from drift.backtest.registry import load_plugins, names, strategy_entry
from drift.data.model import DataError
from drift.research.executors import ProcessExecutor, SequentialExecutor, default_workers
from drift.research.portfolios import PortfolioBook
from drift.research.runner import Batch, Executor, RunJob, run_batch
from drift.research.scope import Interval, authorize
from drift.research.settings import (
    COST_PROFILES,
    DEFAULT_CAPITAL,
    apply_overrides,
    check_settings,
    default_settings,
    flatten,
    parse_override,
    parse_value,
)
from drift.research.sources import ArchiveSource, MarketDataSource, SyntheticSource
from drift.research.store import ResultStore

_MAX_SETTINGS_BYTES = 1024 * 1024
_NOTICES = {
    "synthetic": "Synthetic data: validates software only, says nothing about profitability.",
    "development": (
        "Development data, in-sample: bar-open fill proxies with modeled costs, untuned "
        "parameters. A diagnostic, not evidence of an edge."
    ),
    "validation": (
        "Validation data was used: every run is logged, and repeated looks erode its value "
        "as an out-of-sample check."
    ),
}
_TABLE = (
    "strategy",
    "net_pnl",
    "net_return",
    "sharpe",
    "max_drawdown_pct",
    "trades",
    "trades_per_session",
    "win_rate",
    "profit_factor",
    "commissions",
    "run_id",
)


_PORTFOLIO_TABLE = (
    "portfolio_id",
    "strategy",
    "initial_capital",
    "equity",
    "through",
    "net_pnl",
    "sharpe",
    "max_drawdown_pct",
    "trades",
    "continuable",
)


def _market(args: argparse.Namespace) -> MarketDataSource:
    if args.source == "archive":
        return ArchiveSource(args.archive)
    spec = SyntheticSpec(7, "2022-01-03", 262, Decimal("100.00"), 4, 2, 60, 1000, 1)
    return SyntheticSource(
        spec, InstrumentSpec("SYNTH", "XNAS", "equity", "USD", Decimal("0.01"), 1, 1)
    )


def _executor(args: argparse.Namespace, jobs: int) -> Executor:
    if args.sequential:
        if args.workers is not None or args.timeout_seconds is not None:
            raise DataError("--sequential takes no --workers or --timeout-seconds")
        return SequentialExecutor()
    workers = default_workers(jobs) if args.workers is None else args.workers
    return ProcessExecutor(workers, args.timeout_seconds)


def _overrides(args: argparse.Namespace) -> list[tuple[list[str], Any]]:
    pairs: list[tuple[list[str], Any]] = []
    if args.settings is not None:
        if args.settings.stat().st_size > _MAX_SETTINGS_BYTES:
            raise DataError("settings file too large")
        loaded = parse_value(args.settings.read_bytes())
        if not isinstance(loaded, dict):
            raise DataError("a settings file holds one JSON object")
        pairs += flatten(loaded)
    return pairs + [parse_override(text) for text in args.set or []]


def _settings(args: argparse.Namespace, strategy: str) -> dict[str, Any]:
    base = default_settings(strategy, capital=args.capital, costs=args.costs)
    return apply_overrides(base, strategy, _overrides(args))


def _notices(roles: tuple[str, ...]) -> str:
    return "\n".join(_NOTICES[role] for role in roles)


def _format(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        if value.is_integer():
            return f"{value:,.0f}"
        return f"{value:,.4f}" if abs(value) < 100 else f"{value:,.2f}"
    return str(value)


def _print_table(rows: list[dict[str, Any]], columns: tuple[str, ...]) -> None:
    cells = [columns, *[tuple(_format(row[c]) for c in columns) for row in rows]]
    widths = [max(len(line[i]) for line in cells) for i in range(len(columns))]
    for line in cells:
        print("  ".join(cell.ljust(width) for cell, width in zip(line, widths, strict=True)))


def _require_column(store: ResultStore, column: str) -> None:
    with store.connect() as db:
        if column not in {row[0] for row in db.execute("DESCRIBE comparison").fetchall()}:
            raise DataError(f"unknown column {column}")


def _compare(store: ResultStore, batch_id: str | None, sort: str, as_json: bool = False) -> None:
    _require_column(store, sort)
    with store.connect() as db:
        latest = db.execute(
            "SELECT batch_id FROM batches ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        target = batch_id or (latest[0] if latest else None)
        if target is None:
            raise DataError("no batches yet")
        cursor = db.execute(
            f"""SELECT * FROM comparison WHERE run_id IN
                (SELECT run_id FROM batches WHERE batch_id = ?)
                ORDER BY "{sort}" DESC NULLS LAST""",
            [target],
        )
        headers = [column[0] for column in cursor.description]
        rows = [dict(zip(headers, row, strict=True)) for row in cursor.fetchall()]
    if as_json:
        print(json.dumps(rows, default=str, sort_keys=True))
    else:
        print(f"batch {target}")
        _print_table(rows, _TABLE)


def _report_failures(batch: Batch) -> None:
    for outcome in batch.outcomes:
        if outcome.status != "completed":
            print(f"FAILED {outcome.strategy}: {outcome.error_type}: {outcome.error}")


def _roles(source: MarketDataSource, interval: Interval, allow_validation: bool) -> tuple[str, ...]:
    if source.historical:
        return authorize(interval, allow_validation=allow_validation)
    return ("synthetic",)


def _strategies(_: argparse.Namespace) -> int:
    for name in names():
        entry = strategy_entry(name)
        print(f"{name:22} {entry.family:5} {'replayable' if entry.replayable else 'no-resume'}")
    return 0


def _run(args: argparse.Namespace) -> int:
    load_plugins(args.plugin)
    interval = Interval.select(args.year, args.start, args.end)
    selected = tuple(args.strategies.split(",")) if args.strategies else names()
    source = _market(args)
    roles = _roles(source, interval, args.allow_validation)
    settings = {name: _settings(args, name) for name in selected}
    for name in selected:
        check_settings(name, settings[name])
    store = ResultStore(args.store)
    _require_column(store, args.sort)
    source.verify(interval)
    jobs = [
        RunJob(s, settings[s], interval, source, store.root, roles, None, tuple(args.plugin))
        for s in selected
    ]
    label = f"experiment {interval.start} {interval.end}"
    batch = run_batch(jobs, _executor(args, len(jobs)), store, label=label)
    print(_notices(roles))
    if any(o.run_id for o in batch.outcomes):
        _compare(store, batch.batch_id, args.sort)
    _report_failures(batch)
    return 0 if batch.ok else 1


def _show(args: argparse.Namespace) -> int:
    print(json.dumps(ResultStore(args.store).manifest(args.run_id), sort_keys=True, indent=2))
    return 0


def _compare_command(args: argparse.Namespace) -> int:
    _compare(ResultStore(args.store), args.batch, args.sort, args.json)
    return 0


def _create(args: argparse.Namespace) -> int:
    load_plugins(args.plugin)
    book = PortfolioBook(ResultStore(args.store))
    book.create(args.name, args.strategy, _settings(args, args.strategy))
    print(f"created portfolio {args.name}: {args.strategy}, capital {args.capital} USD")
    return 0


def _configure(args: argparse.Namespace) -> int:
    load_plugins(args.plugin)
    book = PortfolioBook(ResultStore(args.store))
    print(f"{args.name}: configuration version {book.configure(args.name, _overrides(args))}")
    return 0


def _advance(args: argparse.Namespace) -> int:
    load_plugins(args.plugin)
    store = ResultStore(args.store)
    book = PortfolioBook(store)
    source = _market(args)
    if args.year is not None and args.end:
        raise DataError("choose --year or --end, not both")
    end = f"{args.year:04d}-12-31" if args.year is not None else args.end
    if end is None:
        raise DataError("choose --year or --end")
    plans: list[RunJob] = []
    for name in args.names:
        history = book.get(name).segments
        start = args.start
        if start is None and args.year is not None and not history:
            start = f"{args.year:04d}-01-01"
        plans.append(
            book.plan(
                name,
                source,
                start=start,
                end=end,
                allow_validation=args.allow_validation,
                accept_code_change=args.accept_code_change,
                plugins=tuple(args.plugin),
            )
        )
    for window in {
        Interval(job.lineage.inception, job.interval.end) for job in plans if job.lineage
    }:
        source.verify(window)
    batch = run_batch(plans, _executor(args, len(plans)), store, label=f"portfolio through {end}")
    print(_notices(tuple(dict.fromkeys(r for job in plans for r in job.roles))))
    rows = []
    committed = True
    for job, outcome in zip(plans, batch.outcomes, strict=True):
        if outcome.status != "completed" or job.lineage is None:
            continue
        try:
            book.commit(job, outcome)
        except DataError as exc:  # one lost race must not hold back the other portfolios
            print(f"NOT COMMITTED {job.lineage.portfolio_id}: {exc}")
            committed = False
            continue
        report = book.report(job.lineage.portfolio_id)
        rows.append(report | report["metrics"] | {"run_id": outcome.run_id})
    if rows:
        _print_table(
            rows,
            (
                "portfolio_id",
                "strategy",
                "through",
                "equity",
                "net_pnl",
                "sharpe",
                "max_drawdown_pct",
                "trades",
                "continuable",
                "run_id",
            ),
        )
    _report_failures(batch)
    return 0 if batch.ok and committed else 1


def _list(args: argparse.Namespace) -> int:
    book = PortfolioBook(ResultStore(args.store))
    reports = [book.report(name) for name in book.names()]
    rows = [report | report["metrics"] for report in reports]
    if rows:
        _print_table(
            rows,
            _PORTFOLIO_TABLE,
        )
    else:
        print("no portfolios")
    return 0


def _portfolio_show(args: argparse.Namespace) -> int:
    print(json.dumps(PortfolioBook(ResultStore(args.store)).report(args.name), indent=2))
    return 0


def _parser() -> argparse.ArgumentParser:
    store = argparse.ArgumentParser(add_help=False)
    store.add_argument("--store", type=Path, default=Path("data/research"), help="results root")
    market = argparse.ArgumentParser(add_help=False)
    market.add_argument("--source", choices=("archive", "synthetic"), default="archive")
    market.add_argument("--archive", type=Path, default=Path("data/nvda-history"))
    market.add_argument("--allow-validation", action="store_true", help="opt in to 2023 data")
    market.add_argument(
        "--plugin", action="append", default=[], help="module registering strategies"
    )
    workers = argparse.ArgumentParser(add_help=False)
    workers.add_argument("--workers", type=int, help="concurrent processes (default: up to 4)")
    workers.add_argument("--sequential", action="store_true", help="in this process, one by one")
    workers.add_argument("--timeout-seconds", type=float, help="per-strategy time limit")
    overrides = argparse.ArgumentParser(add_help=False)
    overrides.add_argument(
        "--set", action="append", help="override, e.g. orb.params.horizon_seconds=900"
    )
    overrides.add_argument("--settings", type=Path, help="JSON file of overrides")
    profile = argparse.ArgumentParser(add_help=False)
    profile.add_argument("--capital", default=DEFAULT_CAPITAL, help="USD per strategy")
    profile.add_argument("--costs", choices=tuple(COST_PROFILES), default="base")

    parser = argparse.ArgumentParser(prog="drift", description=__doc__)
    groups = parser.add_subparsers(dest="group", required=True)
    research = groups.add_parser("research", help="independent experiments")
    commands = research.add_subparsers(dest="command", required=True)
    commands.add_parser("strategies", help="list registered strategies").set_defaults(
        run=_strategies
    )
    run = commands.add_parser(
        "run", parents=[store, market, workers, overrides, profile], help="run strategies"
    )
    run.add_argument("--year", type=int)
    run.add_argument("--start")
    run.add_argument("--end")
    run.add_argument("--strategies", help="comma-separated; default: all registered")
    run.add_argument("--sort", default="net_pnl")
    run.set_defaults(run=_run)
    compare = commands.add_parser("compare", parents=[store], help="compare a batch's runs")
    compare.add_argument("--batch", help="default: the latest batch")
    compare.add_argument("--sort", default="net_pnl")
    compare.add_argument("--json", action="store_true")
    compare.set_defaults(run=_compare_command)
    show = commands.add_parser("show", parents=[store], help="print a run's manifest")
    show.add_argument("run_id")
    show.set_defaults(run=_show)

    portfolio = groups.add_parser("portfolio", help="persistent virtual portfolios")
    actions = portfolio.add_subparsers(dest="command", required=True)
    create = actions.add_parser("create", parents=[store, overrides, profile], help="new portfolio")
    create.add_argument("name")
    create.add_argument("--strategy", required=True)
    create.add_argument("--plugin", action="append", default=[])
    create.set_defaults(run=_create)
    configure = actions.add_parser(
        "configure", parents=[store, overrides], help="new settings for later segments"
    )
    configure.add_argument("name")
    configure.add_argument("--plugin", action="append", default=[])
    configure.set_defaults(run=_configure)
    advance = actions.add_parser(
        "advance", parents=[store, market, workers], help="simulate the next segment"
    )
    advance.add_argument("names", nargs="+")
    advance.add_argument("--year", type=int, help="through the end of this year")
    advance.add_argument("--start", help="first segment only")
    advance.add_argument("--end")
    advance.add_argument("--accept-code-change", action="store_true")
    advance.set_defaults(run=_advance)
    actions.add_parser("list", parents=[store], help="all portfolios").set_defaults(run=_list)
    show = actions.add_parser("show", parents=[store], help="a portfolio's whole history")
    show.add_argument("name")
    show.set_defaults(run=_portfolio_show)
    return parser


def main(argv: list[str]) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        code: int = args.run(args)
        return code
    except (DataError, ValueError, ArithmeticError, RecursionError) as exc:
        print(f"drift: {exc}")
        return 2
    except OSError:
        print("drift: local file operation failed")
        return 2
