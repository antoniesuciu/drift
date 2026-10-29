"""Run the synthetic engine check; no trading or network modes are exposed."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from quantlab import __version__


def main() -> None:
    parser = argparse.ArgumentParser(description="QuantLab offline foundation checks")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("command", choices=["smoke", "data-demo", "data-ingest", "data-replay"])
    parser.add_argument("--request", type=Path, help="local synthetic request JSON")
    parser.add_argument("--output", type=Path, help="local data storage root")
    parser.add_argument("--dataset", type=Path, help="published dataset directory")
    args = parser.parse_args()

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
