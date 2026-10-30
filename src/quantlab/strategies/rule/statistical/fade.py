"""Edge-triggered band fade shared by the mean-reversion variants (VWAP and Bollinger).

A variant supplies a z-score for each new reading; this core turns a fresh crossing of
+/- `sigma_multiple` inside the trading window into a fade (stretched up -> SHORT, stretched
down -> LONG). Only crossings trigger, so a price that stays outside the band does not repeat
the signal, and a reading that is undefined (warm-up, zero dispersion, gap) clears the state.
"""

from dataclasses import dataclass
from decimal import Decimal

from quantlab.data.model import DataError, local_ns
from quantlab.strategies.calendar import Calendar
from quantlab.strategies.market import Candle
from quantlab.strategies.proposal import Intent, Proposal, new_proposal
from quantlab.strategies.rule.statistical.session import check_clock


@dataclass(frozen=True, slots=True)
class FadeParams:
    window_start: str = "11:30"  # New York wall clock; the research text gives 17:30-20:00 CET
    window_end: str = "14:00"
    sigma_multiple: Decimal = Decimal("2.0")
    allow_long: bool = True
    allow_short: bool = True
    horizon_seconds: int = 1200
    entry_valid_seconds: int = 300

    def __post_init__(self) -> None:
        check_clock(self.window_start)
        check_clock(self.window_end)
        if self.window_start >= self.window_end:
            raise DataError("window must start before it ends")
        if self.sigma_multiple <= 0 or self.horizon_seconds < 1 or self.entry_valid_seconds < 1:
            raise DataError("sigma multiple, horizon and entry validity must be positive")
        if not (self.allow_long or self.allow_short):
            raise DataError("at least one direction must be allowed")


class FadeRule:
    def __init__(
        self,
        params: FadeParams,
        instrument_id: str,
        calendar: Calendar,
        *,
        strategy_id: str,
        agent_id: str,
        version: str,
    ) -> None:
        self.params, self.instrument_id, self.calendar = params, instrument_id, calendar
        self.strategy_id, self.agent_id, self.version = strategy_id, agent_id, version
        self._prev: Decimal | None = None

    def _signal(self, c: Candle, z: Decimal | None, note: str) -> Proposal | None:
        prev, self._prev = self._prev, z
        if z is None or prev is None:
            return None
        k = self.params.sigma_multiple
        if prev < k <= z:
            intent = Intent.SHORT
        elif prev > -k >= z:
            intent = Intent.LONG
        else:
            return None
        start = local_ns(c.day, self.params.window_start)
        if not start <= c.end <= local_ns(c.day, self.params.window_end):
            return None
        reasons: tuple[str, ...] = ()
        if not (self.params.allow_short if intent == Intent.SHORT else self.params.allow_long):
            intent, reasons = Intent.NO_TRADE, ("direction_disabled",)
        return new_proposal(
            agent_id=self.agent_id,
            strategy_id=self.strategy_id,
            instrument_id=self.instrument_id,
            version=self.version,
            generated_at=c.available,
            valid_seconds=self.params.entry_valid_seconds,
            horizon_seconds=self.params.horizon_seconds,
            intent=intent,
            rationale=f"z={format(z, '.2f')} {note}",
            reasons=reasons,
            refs=(f"session:{c.day}", f"candle_end:{c.end}"),
        )
