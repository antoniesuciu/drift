"""Trend following: dual simple-moving-average crossover on completed N-minute candles.

fast = SMA of the last `fast` closes, slow = SMA of the last `slow` closes, both within the
session. A fresh cross of fast above slow (previously fast <= slow) proposes LONG; fast below
slow (previously fast >= slow) proposes SHORT. The position leaves on the opposite cross
(`exit_on_opposite`) or at the session flatten; it does not reverse in the same step. Windows
never span sessions or a missing bucket, so the first signal needs `slow + 1` same-session bars.
"""

from collections import deque
from dataclasses import dataclass
from decimal import Decimal

from drift.data.model import SECOND, DataError
from drift.strategies.calendar import Calendar
from drift.strategies.market import TIMEFRAMES, Aggregator, Candle
from drift.strategies.proposal import Intent, Proposal, new_proposal

TREND_VERSION = "TREND-SMA-v1"


@dataclass(frozen=True, slots=True)
class TrendParams:
    timeframe: int = 5
    fast: int = 5
    slow: int = 20
    allow_long: bool = True
    allow_short: bool = True
    entry_valid_seconds: int = 300

    def __post_init__(self) -> None:
        if self.timeframe not in TIMEFRAMES or not 1 <= self.fast < self.slow:
            raise DataError("timeframe must be 1m/5m/15m/30m/1h and 1 <= fast < slow")
        if self.entry_valid_seconds < 1 or not (self.allow_long or self.allow_short):
            raise DataError("entry validity must be positive and one direction allowed")


class TrendRule:
    def __init__(self, params: TrendParams, instrument_id: str, calendar: Calendar) -> None:
        self.params, self.instrument_id, self.calendar = params, instrument_id, calendar
        self.agent_id, self.strategy_id = "trend-001", "TREND-SMA"
        self._agg = Aggregator(params.timeframe, calendar)
        self._closes: deque[Decimal] = deque(maxlen=params.slow + 1)
        self._last: Candle | None = None

    def _sma(self, n: int, back: int) -> Decimal:
        window = list(self._closes)
        end = len(window) - back
        return sum(window[end - n : end], Decimal(0)) / n

    def on_candle(self, c: Candle) -> Proposal | None:
        k = self._agg.push(c)
        if k is None:
            return None
        last, self._last = self._last, k
        if last is None or last.day != k.day or last.end != k.start:
            self._closes.clear()
        self._closes.append(k.close)
        p = self.params
        if len(self._closes) < p.slow + 1:
            return None
        fast, slow = self._sma(p.fast, 0), self._sma(p.slow, 0)
        fast_prev, slow_prev = self._sma(p.fast, 1), self._sma(p.slow, 1)
        if fast_prev <= slow_prev and fast > slow:
            intent = Intent.LONG
        elif fast_prev >= slow_prev and fast < slow:
            intent = Intent.SHORT
        else:
            return None
        reasons: tuple[str, ...] = ()
        if not (p.allow_long if intent == Intent.LONG else p.allow_short):
            # no new position that way, but the cross still ends one held the other way
            intent, reasons = Intent.FLAT, ("direction_disabled",)
        session = self.calendar.get(c.day)
        remaining = max((session.close if session else c.available) - c.available, 0) // SECOND
        return new_proposal(
            agent_id=self.agent_id,
            strategy_id=self.strategy_id,
            instrument_id=self.instrument_id,
            version=TREND_VERSION,
            generated_at=c.available,
            valid_seconds=p.entry_valid_seconds,
            horizon_seconds=remaining,
            intent=intent,
            rationale=f"sma{p.fast}={format(fast, '.4f')} sma{p.slow}={format(slow, '.4f')}",
            reasons=reasons,
            refs=(f"session:{c.day}", f"candle_end:{k.end}"),
        )
