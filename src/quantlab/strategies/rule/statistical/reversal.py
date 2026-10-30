"""Short-term reversal (project audit, appendix D): fade the trailing N-minute return.

On each completed `timeframe` candle (aligned to the session open) the return close/open - 1
is computed; a negative return proposes LONG and a positive one SHORT, the opposite of the
move, provided |return| reaches `min_abs_return_bps`. Entry is the next available executable
bar and the exit is the time horizon (15 minutes by default). Setting `allow_short` false gives
the audit's long/flat control. Non-overlapping buckets keep successive signals independent.
"""

from dataclasses import dataclass
from decimal import Decimal

from quantlab.data.model import DataError
from quantlab.strategies.calendar import Calendar
from quantlab.strategies.market import TIMEFRAMES, Aggregator, Candle
from quantlab.strategies.proposal import Intent, Proposal, new_proposal

REVERSAL_VERSION = "REVERSAL-v1"


@dataclass(frozen=True, slots=True)
class ReversalParams:
    timeframe: int = 15
    min_abs_return_bps: Decimal = Decimal(0)
    allow_long: bool = True
    allow_short: bool = True
    horizon_seconds: int = 900
    entry_valid_seconds: int = 300

    def __post_init__(self) -> None:
        if self.timeframe not in TIMEFRAMES or self.min_abs_return_bps < 0:
            raise DataError("timeframe must be 1m/5m/15m/30m/1h and the threshold non-negative")
        if self.horizon_seconds < 1 or self.entry_valid_seconds < 1:
            raise DataError("horizon and entry validity must be positive")
        if not (self.allow_long or self.allow_short):
            raise DataError("at least one direction must be allowed")


class ReversalRule:
    def __init__(self, params: ReversalParams, instrument_id: str, calendar: Calendar) -> None:
        self.params, self.instrument_id = params, instrument_id
        self.agent_id, self.strategy_id = "rev-001", "REVERSAL"
        self._agg = Aggregator(params.timeframe, calendar)

    def on_candle(self, c: Candle) -> Proposal | None:
        k = self._agg.push(c)
        if k is None:
            return None
        move = k.close / k.open - 1
        if move == 0 or abs(move) * 10_000 < self.params.min_abs_return_bps:
            return None
        intent = Intent.LONG if move < 0 else Intent.SHORT
        reasons: tuple[str, ...] = ()
        if not (self.params.allow_long if intent == Intent.LONG else self.params.allow_short):
            intent, reasons = Intent.NO_TRADE, ("direction_disabled",)
        return new_proposal(
            agent_id=self.agent_id,
            strategy_id=self.strategy_id,
            instrument_id=self.instrument_id,
            version=REVERSAL_VERSION,
            generated_at=c.available,
            valid_seconds=self.params.entry_valid_seconds,
            horizon_seconds=self.params.horizon_seconds,
            intent=intent,
            rationale=f"{self.params.timeframe}m_return={move:.6f}",
            reasons=reasons,
            refs=(f"session:{c.day}", f"candle_end:{k.end}"),
        )
