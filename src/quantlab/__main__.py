"""Offline synthetic checks and backtests; no live, broker or network modes are exposed."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from quantlab import __version__

MAX_CONFIG_BYTES = 1024 * 1024


def _backtest(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    from quantlab.backtest.config import BacktestConfig, default_config
    from quantlab.backtest.engine import run_backtest
    from quantlab.data.model import DataError

    if args.dump_config:
        print(json.dumps(default_config(args.strategy), sort_keys=True, indent=2))
        return
    try:
        if args.config and args.config.stat().st_size > MAX_CONFIG_BYTES:
            raise DataError("configuration file too large")
        raw = json.loads(args.config.read_bytes()) if args.config else default_config(args.strategy)
        result = run_backtest(BacktestConfig.parse(raw))
        if args.output is not None:
            result.write(args.output)
    except (DataError, ValueError, ArithmeticError, RecursionError) as exc:
        parser.exit(2, f"quantlab: {exc}\n")
    except OSError:
        parser.exit(2, "quantlab: local file operation failed\n")
    if args.json:
        print(json.dumps(result.to_dict(), sort_keys=True))
    else:
        print(result.markdown(), end="")
    if not result.reconciliation["ok"]:
        parser.exit(2, "quantlab: engine and ledger balances do not reconcile\n")


def main() -> None:
    from quantlab.backtest.config import STRATEGIES

    parser = argparse.ArgumentParser(description="QuantLab offline foundation checks")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument(
        "command", choices=["smoke", "data-demo", "data-ingest", "data-replay", "backtest"]
    )
    parser.add_argument("--request", type=Path, help="local synthetic request JSON")
    parser.add_argument("--output", type=Path, help="local data storage root")
    parser.add_argument("--dataset", type=Path, help="published dataset directory")
    parser.add_argument("--config", type=Path, help="backtest configuration JSON")
    parser.add_argument("--strategy", choices=STRATEGIES, help="built-in demo setup")
    parser.add_argument("--dump-config", action="store_true", help="print the demo configuration")
    parser.add_argument("--json", action="store_true", help="print the full report as JSON")
    args = parser.parse_args()

    backtest_only = (args.config, args.strategy, args.dump_config or None, args.json or None)
    if args.command != "backtest" and any(v is not None for v in backtest_only):
        parser.error("--config, --strategy, --dump-config and --json apply to backtest only")
    if args.command == "backtest":
        if args.dataset is not None or args.request is not None:
            parser.error("backtest takes --config or --strategy, with optional --output/--json")
        if (args.config is None) == (args.strategy is None):
            parser.error("backtest requires exactly one of --config or --strategy")
        if args.dump_config and (args.config is not None or args.output is not None):
            parser.error("--dump-config only combines with --strategy")
        _backtest(parser, args)
        return

    if args.command != "smoke":
        from quantlab.data.model import DataError
        from quantlab.data.replay import replay_dataset
        from quantlab.data.store import ingest
        from quantlab.data.synthetic import write_demo

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
            parser.exit(2, f"quantlab: {exc}\n")
        except OSError:
            parser.exit(2, "quantlab: local storage operation failed\n")
        return
    if args.request is not None or args.output is not None or args.dataset is not None:
        parser.error("smoke takes no data arguments")

    from quantlab.smoke import run_smoke

    print(json.dumps(asdict(run_smoke()), sort_keys=True))


if __name__ == "__main__":
    main()
