"""Explicitly authorized historical download and offline dataset inspection."""

import argparse
import json
from pathlib import Path
from typing import Any

from drift.data.alpaca import AlpacaClient, Credentials
from drift.data.equity import PilotRequest
from drift.data.equity_store import acquire, load
from drift.data.model import DataError


def summary(root: Path) -> dict[str, Any]:
    data, manifest = load(root)
    quality = json.loads((root / "quality.json").read_bytes())
    return {
        "dataset_path": str(root),
        "dataset_id": manifest["dataset_id"],
        "feed": manifest["request"]["feed"],
        "adjustment": "raw",
        "sessions": len(data.calendar.sessions),
        "bars": len(data.candles),
        "missing_minutes": sum(len(s["missing_starts"]) for s in quality["sessions"]),
        "data_sha256": data.sha256,
    }


def run(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    try:
        if args.command == "alpaca-check":
            if args.dataset is None or any(
                (args.request, args.output, args.credentials_file, args.authorize_historical)
            ):
                parser.error("alpaca-check requires only --dataset")
            root = args.dataset
        else:
            if (
                not args.authorize_historical
                or args.credentials_file is None
                or args.request is None
                or args.output is None
                or args.dataset is not None
            ):
                parser.error(
                    "alpaca-fetch requires --authorize-historical, --credentials-file, "
                    "--request and --output; no --dataset"
                )
            if args.request.stat().st_size > 65536:
                raise DataError("pilot request too large")
            request = PilotRequest(**json.loads(args.request.read_bytes()))
            client = AlpacaClient(Credentials.read(args.credentials_file))
            root = acquire(request, client, args.output)
        print(json.dumps(summary(root), sort_keys=True))
    except DataError as exc:
        parser.exit(2, f"drift: {exc}\n")
    except (ValueError, TypeError, OSError):
        parser.exit(2, "drift: invalid request or local file operation failed\n")
