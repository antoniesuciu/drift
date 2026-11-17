"""Strategies a worker imports as a plugin: an ML stand-in, and agents that misbehave on purpose.

They reach the runner the way any future strategy would, through `register` alone.
"""

import os
import random
import time
from dataclasses import dataclass
from typing import Any

from drift.backtest.config import build
from drift.backtest.registry import StrategyEntry, names, register
from drift.backtest.risk import ExitPolicy
from drift.strategies.market import Candle
from drift.strategies.proposal import Intent, Proposal, new_proposal


@dataclass(frozen=True, slots=True)
class Params:
    entry_valid_seconds: int = 300


class Agent:
    """LONG on each session's first candle. Subclasses change one thing."""

    agent_id, strategy_id = "plugin-001", "PLUGIN"
    valid_seconds = 300

    def __init__(self, instrument_id: str) -> None:
        self.instrument_id = instrument_id
        self.day = ""

    def want(self, c: Candle) -> bool:
        fresh, self.day = c.day != self.day, c.day
        return fresh

    def on_candle(self, c: Candle) -> Proposal | None:
        if not self.want(c):
            return None
        return new_proposal(
            agent_id=self.agent_id,
            strategy_id=self.strategy_id,
            instrument_id=self.instrument_id,
            version="PLUGIN-v1",
            generated_at=c.available,
            valid_seconds=self.valid_seconds,
            horizon_seconds=600,
            intent=Intent.LONG,
            rationale="plugin",
            reasons=(),
            refs=(f"candle_end:{c.end}",),
        )


class Crash(Agent):
    def on_candle(self, c: Candle) -> Proposal | None:
        os._exit(13)


class Raise(Agent):
    def on_candle(self, c: Candle) -> Proposal | None:
        raise RuntimeError("strategy bug")


class Hang(Agent):
    def on_candle(self, c: Candle) -> Proposal | None:
        time.sleep(3600)
        return None


class Sleeper(Agent):
    """Logs when it runs, so a test can observe real overlap between processes."""

    done = False

    def on_candle(self, c: Candle) -> Proposal | None:
        if not self.done:
            self.done = True
            with open(os.environ["DRIFT_PROBE"], "a") as log:
                log.write(f"{time.time()} {time.time() + 2.5}\n")
            time.sleep(2.5)
        return None


class Coin(Agent):
    """Depends on a private random stream, so replay cannot rebuild it."""

    def want(self, c: Candle) -> bool:
        return random.random() < 0.01


class LateOrder(Agent):
    """Decides on a session's last bar with a validity that survives the night."""

    valid_seconds = 200_000

    def want(self, c: Candle) -> bool:
        return c.end % 86_400_000_000_000 == 72_000_000_000_000  # 20:00 UTC, the 16:00 EDT close


def _parse(raw: Any) -> tuple[Params, ExitPolicy]:
    return build(Params, raw), ExitPolicy(600)


def _holds_overnight(raw: Any) -> tuple[Params, ExitPolicy]:
    return build(Params, raw), ExitPolicy(10_000_000, None)


_ENTRIES = {
    "probe_ml": ("ML", Agent, _parse, True),
    "crash": ("RULE", Crash, _parse, True),
    "broken": ("RULE", Raise, _parse, True),
    "hang": ("RULE", Hang, _parse, True),
    "sleeper": ("RULE", Sleeper, _parse, True),
    "coin": ("LLM", Coin, _parse, False),
    "holder": ("RULE", Agent, _holds_overnight, True),
    "late_order": ("RULE", LateOrder, _parse, True),
}
for _name, (_family, _agent, _parser, _replayable) in _ENTRIES.items():
    if _name not in names():
        register(
            StrategyEntry(
                _name,
                _family,
                _parser,
                lambda p, i, c, agent=_agent: agent(i.id),
                _replayable,
            )
        )
