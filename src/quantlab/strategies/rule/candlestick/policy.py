"""Candlestick trading policy: maps pattern observations to LONG / SHORT / NO_TRADE proposals.

Directional patterns map by definition (bullish forms long, bearish forms short). Doji and
inside bar are neutral and only become directional when a later completed candle closes beyond
the reference range. Opposing signals abstain; enabled filters must pass; detection order never
decides a trade. Recognition stays in `patterns`.
"""

from collections import deque
from dataclasses import dataclass, field
from decimal import Decimal

from quantlab.data.model import SECOND, DataError, canonical, digest
from quantlab.strategies.calendar import Calendar
from quantlab.strategies.market import TIMEFRAMES, Aggregator, Candle
from quantlab.strategies.proposal import Intent, Proposal
from quantlab.strategies.rule.candlestick.filters import Filters, evaluate_filters
from quantlab.strategies.rule.candlestick.patterns import (
    DETECTOR_VERSION,
    PATTERNS,
    Detection,
    DetectorConfig,
    detect,
)

CANDLE_POLICY_VERSION = "CAND-POLICY-v1"


@dataclass(frozen=True, slots=True)
class CandlestickParams:
    patterns: tuple[str, ...]
    timeframes: tuple[int, ...] = (1,)
    detector: DetectorConfig = field(default_factory=DetectorConfig)
    filters: Filters = field(default_factory=Filters)
    allow_long: bool = True
    allow_short: bool = True
    neutral_confirm_candles: int = 1  # candles allowed for a doji/inside-bar breakout
    span_sessions: bool = False
    horizon_seconds: int = 1800
    entry_valid_seconds: int = 300

    def __post_init__(self) -> None:
        if not self.patterns or not set(self.patterns) <= set(PATTERNS):
            raise DataError("patterns must be a non-empty subset of the detection catalogue")
        if len(set(self.patterns)) != len(self.patterns):
            raise DataError("duplicate pattern")
        if not self.timeframes or not set(self.timeframes) <= set(TIMEFRAMES):
            raise DataError("timeframes must come from 1m, 5m, 15m, 30m, 1h")
        if len(set(self.timeframes)) != len(self.timeframes):
            raise DataError("duplicate timeframe")
        if self.neutral_confirm_candles < 1 or self.entry_valid_seconds < 1:
            raise DataError("confirmation window and entry validity must be positive")
        if self.horizon_seconds < 1 or not (self.allow_long or self.allow_short):
            raise DataError("positive horizon and at least one allowed direction required")

    def version_hash(self) -> str:
        parts = {
            "detector": self.detector.params_hash(),
            "patterns": sorted(self.patterns),
            "timeframes": sorted(self.timeframes),
            "filters": repr(self.filters),
            "span": self.span_sessions,
            "confirm": self.neutral_confirm_candles,
        }
        return digest(canonical(parts))[:16]


@dataclass(slots=True)
class _Setup:
    """A neutral detection waiting for a completed-candle breakout confirmation."""

    detection: Detection
    remaining: int
    cursor: int  # end of the last candle already examined


@dataclass(slots=True)
class CandlestickRule:
    """Maps detections to LONG/SHORT/NO_TRADE; recognition itself stays in `candles`.

    Directional patterns map by definition (bullish forms long, bearish forms short).
    Doji and inside bar are neutral: they only become directional when a later completed
    candle closes beyond the reference range. Opposing signals abstain; enabled filters
    must pass; detection order never decides a trade.
    """

    params: CandlestickParams
    instrument_id: str
    tick: Decimal
    calendar: Calendar
    agent_id: str = "candle-001"
    strategy_id: str = "CANDLESTICK"
    _agg: dict[int, Aggregator] = field(default_factory=dict)
    _hist: dict[int, deque[Candle]] = field(default_factory=dict)
    _setups: dict[int, list[_Setup]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        size = 3 + self.params.filters.max_lookback + 1
        for tf in self.params.timeframes:
            self._agg[tf] = Aggregator(tf, self.calendar)
            self._hist[tf] = deque(maxlen=size)
            self._setups[tf] = []

    def _prior(self, tf: int, span: int) -> list[Candle]:
        before = list(self._hist[tf])[:-span]
        if self.params.span_sessions or not before:
            return before
        day = self._hist[tf][-1].day
        keep: list[Candle] = []
        for k in reversed(before):
            if k.day != day:
                break
            keep.append(k)
        return keep[::-1]

    def on_candle(self, c: Candle) -> Proposal | None:
        p = self.params
        signals: list[tuple[str, str, int]] = []  # (direction, label, timeframe)
        notes: list[str] = []
        for tf in p.timeframes:
            k = self._agg[tf].push(c)
            if k is None:
                continue
            hist = self._hist[tf]
            hist.append(k)
            live: list[_Setup] = []
            for s in self._setups[tf]:
                ok_chain = k.start == s.cursor and (p.span_sessions or k.day == s.detection.day)
                if not ok_chain:
                    continue
                direction = (
                    "long"
                    if k.close > s.detection.ref_high
                    else "short"
                    if k.close < s.detection.ref_low
                    else None
                )
                if direction is None:
                    s.remaining -= 1
                    s.cursor = k.end
                    if s.remaining > 0:
                        live.append(s)
                    continue
                reason = evaluate_filters(p.filters, direction, [k], self._prior(tf, 1), self.tick)
                if reason:
                    notes.append(reason)
                else:
                    signals.append((direction, f"{s.detection.pattern}_breakout", tf))
            self._setups[tf] = live
            for d in detect(p.detector, tuple(hist), p.patterns, p.span_sessions):
                if d.direction == "neutral":
                    self._setups[tf].append(_Setup(d, p.neutral_confirm_candles, k.end))
                    continue
                span = PATTERNS[d.pattern][0]
                reason = evaluate_filters(
                    p.filters, d.direction, list(hist)[-span:], self._prior(tf, span), self.tick
                )
                if reason:
                    notes.append(reason)
                else:
                    signals.append((d.direction, d.pattern, tf))
        if not signals and not notes:
            return None
        allowed = {d for d, ok in (("long", p.allow_long), ("short", p.allow_short)) if ok}
        usable = {s for s in signals if s[0] in allowed}
        if len(usable) != len(signals):
            notes.append("direction_disabled")
        directions = {s[0] for s in usable}
        intent = Intent.NO_TRADE
        if len({s[0] for s in signals}) > 1:  # opposing candidates abstain even if one is disabled
            notes.append("conflicting_signals")
        elif directions == {"long"}:
            intent = Intent.LONG
        elif directions == {"short"}:
            intent = Intent.SHORT
        labels = sorted(f"{s[1]}@{s[2]}m" for s in (usable or set(signals)))
        tag = digest(canonical([labels, notes, str(intent)]))[:12]
        return Proposal(
            f"{self.strategy_id}|{self.instrument_id}|{c.end}|{tag}",
            self.agent_id,
            self.strategy_id,
            self.instrument_id,
            c.available,
            c.available,
            c.available + p.entry_valid_seconds * SECOND,
            p.horizon_seconds,
            intent,
            f"{CANDLE_POLICY_VERSION}:{p.version_hash()}",
            (f"detector:{DETECTOR_VERSION}:{p.detector.params_hash()[:16]}", f"candle_end:{c.end}"),
            ",".join(labels) or "none",
            tuple(sorted(set(notes))),
        )
