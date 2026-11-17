"""Offline research, bounded historical reads and explicitly authorized Alpaca paper runs."""

import argparse
import json
import sys
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

from drift import __version__

MAX_CONFIG_BYTES = 1024 * 1024


def _backtest(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    from drift.backtest.config import BacktestConfig, default_config
    from drift.backtest.engine import run_backtest
    from drift.data.model import DataError

    if args.dump_config:
        try:
            raw = default_config(args.strategy)
            if args.dataset is not None:
                from drift.data.equity_store import backtest_template

                if args.strategy != "itsm":
                    raise DataError("historical pilot admits only the initial ITSM baseline")
                raw = backtest_template(args.dataset)
            print(json.dumps(raw, sort_keys=True, indent=2))
        except (DataError, OSError) as exc:
            parser.exit(2, f"drift: {exc}\n")
        return
    try:
        if args.config and args.config.stat().st_size > MAX_CONFIG_BYTES:
            raise DataError("configuration file too large")
        raw = json.loads(args.config.read_bytes()) if args.config else default_config(args.strategy)
        config = BacktestConfig.parse(raw)
        if args.dataset is not None:
            from drift.backtest.data import HistoricalSpec
            from drift.backtest.engine import run_on
            from drift.data.equity_store import load
            from drift.strategies.rule.statistical.itsm import ItsmParams

            data, manifest = load(args.dataset)
            if not isinstance(config.data, HistoricalSpec) or not isinstance(
                config.strategy.params, ItsmParams
            ):
                raise DataError("historical pilot requires version 2 and the ITSM baseline")
            splits = tuple((s["day"], Decimal(s["ratio"])) for s in manifest["splits"])
            if config.strategy.params.splits != splits:
                raise DataError("ITSM splits must match the dataset's reviewed action evidence")
            result = run_on(config, data)
        else:
            result = run_backtest(config)
        if args.output is not None:
            result.write(args.output)
    except (DataError, ValueError, ArithmeticError, RecursionError) as exc:
        parser.exit(2, f"drift: {exc}\n")
    except OSError:
        parser.exit(2, "drift: local file operation failed\n")
    if args.json:
        print(json.dumps(result.to_dict(), sort_keys=True))
    else:
        print(result.markdown(), end="")
    if not result.reconciliation["ok"]:
        parser.exit(2, "drift: engine and ledger balances do not reconcile\n")


def main() -> None:
    if sys.argv[1:2] in (["research"], ["portfolio"]):
        from drift.research.cli import main as research

        sys.exit(research(sys.argv[1:]))

    from drift.backtest.config import STRATEGIES

    parser = argparse.ArgumentParser(
        description="Drift offline foundation checks; see also `drift research --help` "
        "and `drift portfolio --help`"
    )
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument(
        "command",
        choices=[
            "smoke",
            "data-demo",
            "data-ingest",
            "data-replay",
            "backtest",
            "alpaca-fetch",
            "alpaca-check",
            "paper-status",
            "paper-run",
            "paper-kill",
        ],
    )
    parser.add_argument("--request", type=Path, help="local synthetic request JSON")
    parser.add_argument("--output", type=Path, help="local data storage root")
    parser.add_argument("--dataset", type=Path, help="published dataset directory")
    parser.add_argument("--config", type=Path, help="backtest configuration JSON")
    parser.add_argument("--strategy", choices=STRATEGIES, help="built-in demo setup")
    parser.add_argument("--dump-config", action="store_true", help="print the demo configuration")
    parser.add_argument("--json", action="store_true", help="print the full report as JSON")
    parser.add_argument("--credentials-file", type=Path, help="explicit Alpaca paper dotenv path")
    parser.add_argument("--authorize-paper-connection", action="store_true")
    parser.add_argument("--authorize-paper-orders", action="store_true")
    parser.add_argument("--resume-paper", action="store_true", help="resume after reconciliation")
    parser.add_argument("--max-seconds", type=int, default=25200, help="bounded paper run duration")
    parser.add_argument(
        "--authorize-historical",
        action="store_true",
        help="authorize free historical reads and private pilot storage",
    )
    args = parser.parse_args()

    if args.command.startswith("paper-"):
        if any(
            (
                args.request,
                args.dataset,
                args.config,
                args.strategy,
                args.dump_config,
                args.json,
                args.authorize_historical,
            )
        ):
            parser.error("paper commands do not accept historical/backtest arguments")
        from drift.execution.alpaca_cli import run as paper_run

        paper_run(parser, args)
        return
    if args.authorize_paper_connection or args.authorize_paper_orders or args.resume_paper:
        parser.error("paper authorization/resume flags require a paper command")

    if args.command != "alpaca-fetch" and (args.credentials_file or args.authorize_historical):
        parser.error("Alpaca credentials/authorization apply to alpaca-fetch only")
    if args.command in ("alpaca-fetch", "alpaca-check"):
        if args.config or args.strategy or args.dump_config or args.json:
            parser.error("Alpaca data commands do not accept backtest arguments")
        from drift.data.alpaca_cli import run

        run(parser, args)
        return

    backtest_only = (args.config, args.strategy, args.dump_config or None, args.json or None)
    if args.command != "backtest" and any(v is not None for v in backtest_only):
        parser.error("--config, --strategy, --dump-config and --json apply to backtest only")
    if args.command == "backtest":
        if args.request is not None or (
            args.dataset is not None and args.config is None and not args.dump_config
        ):
            parser.error("backtest takes --config or --strategy, with optional --output/--json")
        if (args.config is None) == (args.strategy is None):
            parser.error("backtest requires exactly one of --config or --strategy")
        if args.dump_config and (args.config is not None or args.output is not None):
            parser.error("--dump-config only combines with --strategy")
        _backtest(parser, args)
        return

    if args.command != "smoke":
        from drift.data.model import DataError
        from drift.data.replay import replay_dataset
        from drift.data.store import ingest
        from drift.data.synthetic import write_demo

        try:
            if args.command == "data-replay":
                if args.dataset is None or args.output is not None or args.request is not None:
                    parser.error("data-replay requires only --dataset")
                report = replay_dataset(args.dataset)
            else:
                if args.output is None or args.dataset is not None:
                    parser.error("data ingestion requires --output and no --dataset")
                request = args.request
                if args.command == "data-demo":
                    if request is not None:
                        parser.error("data-demo does not accept --request")
                    fixtures = args.output / "synthetic-input"
                    request = (
                        fixtures / "request.json" if fixtures.exists() else write_demo(fixtures)
                    )
                if request is None:
                    parser.error("data-ingest requires --request")
                published = ingest(request, args.output)
                report = {"dataset_path": str(published), "dataset_version": published.name}
                if args.command == "data-demo":
                    report |= replay_dataset(published)
            print(json.dumps(report, sort_keys=True))
        except DataError as exc:
            parser.exit(2, f"drift: {exc}\n")
        except OSError:
            parser.exit(2, "drift: local storage operation failed\n")
        return
    if args.request is not None or args.output is not None or args.dataset is not None:
        parser.error("smoke takes no data arguments")

    from drift.smoke import run_smoke

    print(json.dumps(asdict(run_smoke()), sort_keys=True))


if __name__ == "__main__":
    main()
