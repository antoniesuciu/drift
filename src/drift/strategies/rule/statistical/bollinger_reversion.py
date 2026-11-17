"""Mean reversion to Bollinger bands on completed N-minute candles.

Middle band = simple moving average of the last `period` closes of the same session, upper and
lower = middle +/- k x population standard deviation of those closes (the current close is
included, as in the standard definition). z = (close - middle) / sigma; a fresh +/-k crossing
inside the window is faded. Windows never span sessions or a missing bucket.
"""

from collections import deque
from dataclasses import dataclass
from decimal import Decimal

from drift.data.model import DataError
from drift.strategies.calendar import Calendar
from drift.strategies.market import TIMEFRAMES, Aggregator, Candle
from drift.strategies.proposal import Proposal
from drift.strategies.rule.statistical.fade import FadeParams, FadeRule

BOLLINGER_VERSION = "BOLL-REV-v1"


@dataclass(frozen=True, slots=True)
class BollingerParams(FadeParams):
    timeframe: int = 5
    period: int = 20

    def __post_init__(self) -> None:
        FadeParams.__post_init__(self)
        if self.timeframe not in TIMEFRAMES or self.period < 2:
            raise DataError("timeframe must be 1m/5m/15m/30m/1h and period at least 2")


class BollingerReversionRule(FadeRule):
    def __init__(self, params: BollingerParams, instrument_id: str, calendar: Calendar) -> None:
        super().__init__(
            params,
            instrument_id,
            calendar,
            strategy_id="BOLL-REV",
            agent_id="boll-001",
            version=BOLLINGER_VERSION,
        )
        self._period = params.period
        self._agg = Aggregator(params.timeframe, calendar)
        self._closes: deque[Decimal] = deque(maxlen=params.period)
        self._last: Candle | None = None

    def on_candle(self, c: Candle) -> Proposal | None:
        k = self._agg.push(c)
        if k is None:
            return None
        last, self._last = self._last, k
        if last is None or last.day != k.day or last.end != k.start:
            self._closes.clear()  # new session or a missing bucket: restart the window
        self._closes.append(k.close)
        z: Decimal | None = None
        note = "boll=warmup"
        if len(self._closes) == self._period:
            mean = sum(self._closes, Decimal(0)) / self._period
            var = sum(((x - mean) ** 2 for x in self._closes), Decimal(0)) / self._period
            sigma = var.sqrt()
            note = f"mid={format(mean, '.4f')}"
            if sigma > 0:
                z = (k.close - mean) / sigma
        return self._signal(c, z, note)
