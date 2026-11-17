"""Strategy registry: all the backtest layer knows about a strategy.

An entry says how to validate a strategy's parameters and how to build its agent. The config
parser, the engine and the research runner read only this table, so a new rule, ML or LLM
strategy needs one `register` call and no change to them. A module outside the package
registers itself when imported; `load_plugins` does that in each worker process.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any

from drift.backtest.data import InstrumentSpec
from drift.backtest.risk import ExitPolicy
from drift.data.model import DataError, digest, token
from drift.strategies.calendar import Calendar
from drift.strategies.proposal import FAMILIES


@dataclass(frozen=True, slots=True)
class StrategyEntry:
    """`parse` turns a JSON object into (params, default exit policy); `make` builds a fresh agent.

    `replayable` promises the agent's state is a pure function of its parameters and the candles
    it has seen. Portfolio continuation relies on that; a non-deterministic agent must say False.
    `needs_splits` asks the runner to pass the dataset's reviewed splits as a `splits` parameter.
    `split_safe` says whether these parameters stay meaningful across a split on raw prices and
    volumes. It defaults to False: a strategy claims it, and a window with a split is refused
    otherwise, because a comparison across one is silently wrong rather than visibly broken.
    """

    name: str
    family: str
    parse: Callable[[Any], tuple[Any, ExitPolicy]]
    make: Callable[[Any, InstrumentSpec, Calendar], Any]
    replayable: bool = True
    needs_splits: bool = False
    split_safe: Callable[[Any], bool] = lambda params: False


_REGISTRY: dict[str, StrategyEntry] = {}


def register(entry: StrategyEntry) -> None:
    token(entry.name)
    if entry.family not in FAMILIES or entry.name in _REGISTRY:
        raise DataError("a strategy needs a known family and a unique name")
    _REGISTRY[entry.name] = entry


def strategy_entry(name: str) -> StrategyEntry:
    entry = _REGISTRY.get(name)
    if entry is None:
        raise DataError("unknown strategy")
    return entry


def names() -> tuple[str, ...]:
    return tuple(_REGISTRY)


def plugin_digests(modules: Iterable[str]) -> dict[str, str]:
    """Source hash per plugin, so a run's identity covers code outside the package."""
    return {m: digest(Path(str(import_module(m).__file__)).read_bytes()) for m in sorted(modules)}


def load_plugins(modules: Iterable[str]) -> None:
    """Import modules that register strategies; idempotent, as imports are."""
    for module in modules:
        try:
            import_module(module)
        except ImportError as exc:
            raise DataError(f"cannot import strategy plugin {module}") from exc
