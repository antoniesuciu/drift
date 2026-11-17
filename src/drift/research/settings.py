"""What a run is configured with, before it meets its data.

Settings are plain JSON so a portfolio can store every version of them. Defaults exist only
here, in one reviewed place: capital is $20,000 and costs are a named profile, never absent.
Spread and slippage figures are assumptions (the archive holds no quotes), and the commission
inputs are those of docs/COSTS_AND_PROVIDERS.md, not an era-specific fee schedule.
"""

import json
from dataclasses import asdict
from decimal import Decimal
from typing import Any

from drift.backtest.config import BacktestConfig, default_config, plain
from drift.backtest.registry import names, strategy_entry
from drift.data.model import DataError
from drift.research.sources import Piece

DEFAULT_CAPITAL = "20000"
SECTIONS = ("execution", "sizing", "risk", "params", "exit")
COST_PROFILES: dict[str, dict[str, Any]] = {
    "zero": {
        "half_spread_ticks": 0,
        "slippage_ticks": 0,
        "order_latency_seconds": 0,
        "per_unit": "0",
        "min_per_order": "0",
        "max_pct_notional": None,
        "sell_pct_notional": "0",
        "half_spread_bps": "0",
        "slippage_bps": "0",
    },
    "base": {
        "half_spread_ticks": 0,
        "slippage_ticks": 0,
        "order_latency_seconds": 0,
        "per_unit": "0.0035",
        "min_per_order": "0.35",
        "max_pct_notional": "0.01",
        "sell_pct_notional": "0.0000206",
        "half_spread_bps": "1",
        "slippage_bps": "1",
    },
    "stressed": {
        "half_spread_ticks": 0,
        "slippage_ticks": 0,
        "order_latency_seconds": 30,
        "per_unit": "0.005",
        "min_per_order": "1",
        "max_pct_notional": "0.01",
        "sell_pct_notional": "0.0000206",
        "half_spread_bps": "3",
        "slippage_bps": "3",
    },
}


def default_settings(
    strategy: str, *, capital: str = DEFAULT_CAPITAL, costs: str = "base"
) -> dict[str, Any]:
    """Long-only by default: no borrow availability or rate has been verified for shorts."""
    if costs not in COST_PROFILES:
        raise DataError("unknown cost profile")
    demo = default_config(strategy)
    params = demo["strategy"]["params"]
    if getattr(strategy_entry(strategy).parse(params)[0], "allow_short", False):
        params = params | {"allow_short": False}
    amount = Decimal(capital)
    return {
        "capital": capital,
        "execution": dict(COST_PROFILES[costs]),
        "sizing": {"mode": "equity_fraction", "amount": "0.95"},
        "risk": demo["risk"]
        | {
            "max_quantity": "1000000",
            "max_notional": str(amount * 10),
            "max_leverage": "1",
            "max_session_loss": str(amount / 20),
        },
        "params": params,
        "exit": {},
    }


def parse_value(text: str | bytes) -> Any:
    """JSON, except that decimals stay exact text, as money always is here."""
    return json.loads(text, parse_float=str)


def parse_override(text: str) -> tuple[list[str], Any]:
    """`path=value`, where a value that is not JSON is plain text."""
    path, separator, value = text.partition("=")
    if not separator or not path:
        raise DataError("overrides look like execution.slippage_bps=2")
    try:
        return path.split("."), parse_value(value)
    except ValueError:
        return path.split("."), value


def flatten(value: dict[str, Any], prefix: tuple[str, ...] = ()) -> list[tuple[list[str], Any]]:
    """A settings file as overrides, so files and `--set` share one rule set."""
    pairs: list[tuple[list[str], Any]] = []
    for key, item in value.items():
        if isinstance(item, dict):
            pairs += flatten(item, (*prefix, key))
        else:
            pairs.append(([*prefix, key], item))
    return pairs


def apply_overrides(
    settings: dict[str, Any], strategy: str, overrides: list[tuple[list[str], Any]]
) -> dict[str, Any]:
    """A path applies to every strategy; `orb.params.x=1` applies to one. Unknown paths fail."""
    result: dict[str, Any] = json.loads(json.dumps(settings))
    for path, value in overrides:
        keys = list(path)
        if keys[0] in names():
            if keys.pop(0) != strategy:
                continue
        if len(keys) < 2 or keys[0] not in SECTIONS:
            raise DataError("overrides start with " + ", ".join(SECTIONS) + " or a strategy name")
        node = result
        for key in keys[:-1]:
            if not isinstance(node.get(key), dict):
                node[key] = {}
            node = node[key]
        node[keys[-1]] = value
    return result


def cost_label(execution: dict[str, Any]) -> str:
    return next((k for k, v in COST_PROFILES.items() if v == execution), "custom")


def backtest_config(
    strategy: str, settings: dict[str, Any], piece: Piece, *, name: str, capital: str
) -> BacktestConfig:
    """The validated configuration for one window; `exit` overrides the strategy's own policy."""
    instrument = piece.data.instrument
    params = dict(settings["params"])
    if strategy_entry(strategy).needs_splits:
        params["splits"] = [[day, ratio] for day, ratio in piece.splits]
    raw = piece.config | {
        "name": name,
        "instrument": asdict(instrument) | {"tick": str(instrument.tick)},
        "capital": capital,
        "execution": settings["execution"],
        "sizing": settings["sizing"],
        "risk": settings["risk"],
        "strategy": {"name": strategy, "params": params},
    }
    config = BacktestConfig.parse(raw)
    if settings["exit"]:
        raw["strategy"]["exit"] = plain(config.strategy.exit) | settings["exit"]
        config = BacktestConfig.parse(raw)
    return config


def check_settings(strategy: str, settings: dict[str, Any]) -> None:
    """Refuse bad settings before they are stored or sent to a worker."""
    demo = default_config(strategy)
    raw = demo | {
        "capital": settings["capital"],
        "execution": settings["execution"],
        "sizing": settings["sizing"],
        "risk": settings["risk"],
        "strategy": demo["strategy"] | {"params": settings["params"]},
    }
    config = BacktestConfig.parse(raw)
    if settings["exit"]:
        raw["strategy"]["exit"] = plain(config.strategy.exit) | settings["exit"]
        BacktestConfig.parse(raw)
