"""Family-agnostic strategy contract: RULE, ML and LLM agents all emit shared proposals.

An agent consumes completed candles available at its decision time and returns at most one
`Proposal`. It receives no broker, order or portfolio handle; sizing, risk and execution
belong to the shared backtest layer.
"""

from typing import Protocol

from quantlab.strategies.market import Candle
from quantlab.strategies.proposal import Proposal


class Agent(Protocol):
    agent_id: str
    strategy_id: str

    def on_candle(self, candle: Candle) -> Proposal | None: ...
