"""Run the synthetic engine check; no trading or network modes are exposed."""

import argparse
import json
from dataclasses import asdict

from quantlab import __version__


def main() -> None:
    parser = argparse.ArgumentParser(description="QuantLab offline foundation checks")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("command", choices=["smoke"], help="run a synthetic, order-free replay")
    parser.parse_args()

    from quantlab.smoke import run_smoke

    print(json.dumps(asdict(run_smoke()), sort_keys=True))


if __name__ == "__main__":
    main()
