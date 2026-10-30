"""Mean reversion to the session VWAP (research report 02, hypothesis 4).

z = (close - session VWAP) / volume-weighted standard deviation of typical price around the
VWAP, both accumulated from the open through the latest available candle. A fresh +/-k sigma
extension inside the window is faded; the position leaves by the exit policy (time horizon or
session flatten). The report's regime gates (no scheduled macro release; opening range below a
percentile of 20-day ATR) need data or a definition this lab does not have and are not applied.
"""

from dataclasses import dataclass
from decimal import Decimal

from quantlab.data.model import DataError
from quantlab.strategies.calendar import Calendar
from quantlab.strategies.market import Candle
from quantlab.strategies.proposal import Proposal
from quantlab.strategies.rule.statistical.fade import FadeParams, FadeRule
from quantlab.strategies.rule.statistical.session import SessionTape

VWAP_VERSION = "VWAP-REV-v1"


@dataclass(frozen=True, slots=True)
class VwapParams(FadeParams):
    min_bars: int = 30  # candles since the open before the dispersion is trusted

    def __post_init__(self) -> None:
        FadeParams.__post_init__(self)
        if self.min_bars < 2:
            raise DataError("at least two bars are needed for a dispersion estimate")


class VwapReversionRule(FadeRule):
    def __init__(self, params: VwapParams, instrument_id: str, calendar: Calendar) -> None:
        super().__init__(
            params,
            instrument_id,
            calendar,
            strategy_id="VWAP-REV",
            agent_id="vwap-001",
            version=VWAP_VERSION,
        )
        self._min_bars = params.min_bars
        self._tape = SessionTape(calendar)

    def on_candle(self, c: Candle) -> Proposal | None:
        tape = self._tape
        tape.push(c)
        vwap, std = tape.vwap, tape.vwap_std
        z: Decimal | None = None
        if tape.clean and len(tape.today) >= self._min_bars and vwap is not None and std:
            z = (c.close - vwap) / std
        return self._signal(c, z, f"vwap={format(vwap, '.4f')}" if vwap is not None else "vwap=n/a")
