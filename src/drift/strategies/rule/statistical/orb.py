"""Opening range breakout (research reports 02 and 03).

The opening range is the high and low of the first `range_minutes` (5, 15 or 30) of the cash
session from 09:30 New York. Within the window that ends at `entry_cutoff`, the first completed
candle that closes beyond the range, and passes every enabled filter, proposes LONG (above the
high) or SHORT (below the low); one proposal per session, with a NO_TRADE abstention at the cutoff
when nothing qualified. The exit is the time horizon or session flatten. Optional filters, each
named in the reports with the threshold left as a parameter: opening-range relative volume,
VWAP alignment, breakout-candle volume against the range's average bar volume, and yesterday's
true range below the n-session ATR. Not implemented: catalyst ("stocks in play") selection and
event-free-day filters, which need cross-sectional and calendar data this lab lacks.
"""

from collections import deque
from dataclasses import dataclass
from decimal import Decimal

from drift.data.model import DataError, local_ns
from drift.strategies.calendar import MINUTE_NS, Calendar
from drift.strategies.market import Candle
from drift.strategies.proposal import Intent, Proposal, new_proposal
from drift.strategies.rule.statistical.session import KEEP_DAYS, SessionTape, check_clock

ORB_VERSION = "ORB-v1"


@dataclass(frozen=True, slots=True)
class OrbParams:
    range_minutes: int = 15
    entry_cutoff: str = "11:00"
    allow_long: bool = True
    allow_short: bool = True
    rvol_min: Decimal | None = None  # opening-range volume / mean over prior sessions
    rvol_lookback: int = 20
    vwap_alignment: bool = False  # long needs close > session VWAP, short needs close < VWAP
    breakout_volume_multiple: Decimal | None = None  # vs the range's mean bar volume
    prior_tr_below_atr: int | None = None  # yesterday's true range < ATR over n sessions
    horizon_seconds: int = 1800
    entry_valid_seconds: int = 300

    def __post_init__(self) -> None:
        check_clock(self.entry_cutoff)
        hours, minutes = self.entry_cutoff.split(":")
        if self.range_minutes not in (5, 15, 30):
            raise DataError("range_minutes must be 5, 15 or 30")
        if int(hours) * 60 + int(minutes) <= 9 * 60 + 30 + self.range_minutes:
            raise DataError("the entry cutoff must follow the opening range")
        if (self.rvol_min is not None and self.rvol_min <= 0) or self.rvol_lookback < 1:
            raise DataError("rvol threshold and lookback must be positive")
        if self.breakout_volume_multiple is not None and self.breakout_volume_multiple <= 0:
            raise DataError("breakout volume multiple must be positive")
        if self.prior_tr_below_atr is not None and not 1 <= self.prior_tr_below_atr < KEEP_DAYS:
            raise DataError(f"ATR lookback must be 1 to {KEEP_DAYS - 1} sessions")
        if self.horizon_seconds < 1 or self.entry_valid_seconds < 1:
            raise DataError("horizon and entry validity must be positive")
        if not (self.allow_long or self.allow_short):
            raise DataError("at least one direction must be allowed")


class OrbRule:
    def __init__(self, params: OrbParams, instrument_id: str, calendar: Calendar) -> None:
        self.params, self.instrument_id = params, instrument_id
        self.agent_id, self.strategy_id = "orb-001", "ORB"
        self._tape = SessionTape(calendar)
        self._volumes: deque[int] = deque(maxlen=params.rvol_lookback)
        self._or_end = self._cutoff = 0
        self._range: tuple[Decimal, Decimal, int] | None = None
        self._rvol_reason: str | None = None
        self._done = False
        self._fails: set[str] = set()

    def _new_day(self, day: str) -> None:
        self._or_end = local_ns(day, "09:30") + self.params.range_minutes * MINUTE_NS
        self._cutoff = local_ns(day, self.params.entry_cutoff)
        self._range, self._rvol_reason = None, None
        self._done, self._fails = False, set()

    def _close_range(self) -> None:
        tape, p = self._tape, self.params
        if not tape.clean or len(tape.today) != p.range_minutes:
            self._fails.add("range_incomplete")
            return
        volume = sum(c.volume for c in tape.today)
        self._range = (max(c.high for c in tape.today), min(c.low for c in tape.today), volume)
        if p.rvol_min is not None:
            if len(self._volumes) < p.rvol_lookback:
                self._rvol_reason = "filter_warmup:rvol"
            else:
                mean = Decimal(sum(self._volumes)) / len(self._volumes)
                if mean <= 0:
                    self._rvol_reason = "filter_unavailable:rvol"
                elif Decimal(volume) / mean < p.rvol_min:
                    self._rvol_reason = "filter_failed:rvol"
        self._volumes.append(volume)

    def on_candle(self, c: Candle) -> Proposal | None:
        if self._tape.push(c):
            self._new_day(c.day)
        if c.end == self._or_end:
            self._close_range()
        if c.end <= self._or_end or self._done or c.end > self._cutoff:
            return None
        proposal = self._scan(c)
        if proposal is None and c.end == self._cutoff:
            self._done = True
            if self._range is None:
                self._fails.add("range_incomplete")
            return self._emit(c, Intent.NO_TRADE, "no entry", tuple(self._fails or {"no_breakout"}))
        return proposal

    def _scan(self, c: Candle) -> Proposal | None:
        if self._range is None:
            return None
        high, low, volume = self._range
        p = self.params
        if c.close > high:
            intent = Intent.LONG
        elif c.close < low:
            intent = Intent.SHORT
        else:
            return None
        if not (p.allow_long if intent == Intent.LONG else p.allow_short):
            self._fails.add("direction_disabled")
            return None
        fails: set[str] = set()
        if self._rvol_reason:
            fails.add(self._rvol_reason)
        if p.vwap_alignment:
            vwap = self._tape.vwap
            if vwap is None or not (c.close > vwap if intent == Intent.LONG else c.close < vwap):
                fails.add("filter_failed:vwap")
        if p.breakout_volume_multiple is not None:
            if c.volume < p.breakout_volume_multiple * Decimal(volume) / p.range_minutes:
                fails.add("filter_failed:breakout_volume")
        if p.prior_tr_below_atr is not None:
            pair = self._tape.prior_true_range_vs_atr(p.prior_tr_below_atr)
            if pair is None:
                fails.add("filter_warmup:atr")
            elif pair[0] >= pair[1]:
                fails.add("filter_failed:atr")
        if fails:
            self._fails |= fails
            return None
        self._done = True
        side = "above" if intent == Intent.LONG else "below"
        return self._emit(c, intent, f"close {c.close} {side} range {low}-{high}", ())

    def _emit(
        self, c: Candle, intent: Intent, rationale: str, reasons: tuple[str, ...]
    ) -> Proposal:
        return new_proposal(
            agent_id=self.agent_id,
            strategy_id=self.strategy_id,
            instrument_id=self.instrument_id,
            version=ORB_VERSION,
            generated_at=c.available,
            valid_seconds=self.params.entry_valid_seconds,
            horizon_seconds=self.params.horizon_seconds,
            intent=intent,
            rationale=rationale,
            reasons=reasons,
            refs=(f"session:{c.day}", f"or_end:{self._or_end}", f"candle_end:{c.end}"),
        )
