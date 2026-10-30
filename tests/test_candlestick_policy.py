"""Candlestick policy (M3b): detections to proposals, abstentions, confirmations, causality."""

from collections.abc import Sequence
from decimal import Decimal

import pytest
from helpers import DAY, bar

from quantlab.data.model import DataError
from quantlab.strategies.calendar import Calendar, SessionSpec
from quantlab.strategies.market import Candle
from quantlab.strategies.proposal import Intent, Proposal
from quantlab.strategies.rule.candlestick.filters import Filters, VolumeFilter
from quantlab.strategies.rule.candlestick.policy import CandlestickParams, CandlestickRule

TICK = Decimal("0.01")


def feed(candles: Sequence[Candle], **kwargs: object) -> list[Proposal]:
    params = CandlestickParams(**kwargs)  # type: ignore[arg-type]
    rule = CandlestickRule(params, "SYNTH.XNAS", TICK, Calendar((SessionSpec(DAY),)))
    return [p for c in candles if (p := rule.on_candle(c)) is not None]


def flats(n: int, price: str = "100.00") -> list[Candle]:
    return [bar(price, price, price, price, i=i) for i in range(n)]


BULL_PAIR = [
    ("100.10", "100.12", "99.98", "100.00"),
    ("99.99", "100.20", "99.98", "100.15"),
]
BEAR_PAIR = [
    ("100.00", "100.12", "99.98", "100.10"),
    ("100.11", "100.13", "99.90", "99.95"),
]


def after(prefix: list[Candle], rows: Sequence[tuple[str, ...]], **kw: int) -> list[Candle]:
    return prefix + [bar(*r, i=len(prefix) + j, **kw) for j, r in enumerate(rows)]  # type: ignore[arg-type]


def test_bullish_engulfing_goes_long_when_the_pattern_completes() -> None:
    candles = after(flats(3), BULL_PAIR)
    (p,) = feed(candles, patterns=("bullish_engulfing",))
    assert p.intent == Intent.LONG and p.family == "RULE"
    assert p.generated_at == p.data_asof == candles[-1].available
    assert p.rationale == "bullish_engulfing@1m" and p.reasons == ()
    assert p.valid_until == p.generated_at + 300 * 10**9 and p.horizon_seconds == 1800


def test_bearish_engulfing_goes_short_unless_the_direction_is_disabled() -> None:
    candles = after(flats(3), BEAR_PAIR)
    (p,) = feed(candles, patterns=("bearish_engulfing",))
    assert p.intent == Intent.SHORT
    (blocked,) = feed(candles, patterns=("bearish_engulfing",), allow_short=False)
    assert blocked.intent == Intent.NO_TRADE and blocked.reasons == ("direction_disabled",)


def test_opposing_signals_abstain_whatever_the_detection_order() -> None:
    both = [("100.00", "100.06", "99.99", "100.05"), ("100.06", "100.07", "99.00", "99.99")]
    candles = after(flats(3), both)
    for names in (("hammer", "bearish_engulfing"), ("bearish_engulfing", "hammer")):
        (p,) = feed(candles, patterns=names)
        assert p.intent == Intent.NO_TRADE and p.reasons == ("conflicting_signals",)
        assert p.rationale == "bearish_engulfing@1m,hammer@1m"
    (p,) = feed(candles, patterns=("hammer", "bearish_engulfing"), allow_short=False)
    assert p.intent == Intent.NO_TRADE and "conflicting_signals" in p.reasons


def test_neutral_patterns_need_a_completed_breakout_candle() -> None:
    doji = ("10.00", "10.50", "9.50", "10.02")
    up = ("10.02", "10.65", "10.01", "10.60")
    down = ("10.02", "10.03", "9.30", "9.40")
    inside = ("10.02", "10.40", "9.90", "10.10")
    base = flats(3, "10.00")
    (p,) = feed(after(base, [doji, up]), patterns=("doji",))
    assert p.intent == Intent.LONG and p.rationale == "doji_breakout@1m"
    (p,) = feed(after(base, [doji, down]), patterns=("doji",))
    assert p.intent == Intent.SHORT
    assert feed(after(base, [doji]), patterns=("doji",)) == []  # the doji alone is no signal
    assert feed(after(base, [doji, inside, up]), patterns=("doji",)) == []  # window expired
    (p,) = feed(after(base, [doji, inside, up]), patterns=("doji",), neutral_confirm_candles=2)
    assert p.intent == Intent.LONG
    mother = ("10.0", "10.5", "9.5", "10.0")
    contained = ("10.0", "10.2", "9.8", "10.1")
    (p,) = feed(after(base, [mother, contained, up]), patterns=("inside_bar",))
    assert p.intent == Intent.LONG and p.rationale == "inside_bar_breakout@1m"


def test_enabled_filters_must_pass_and_missing_history_abstains() -> None:
    volume = Filters(volume=VolumeFilter(3, Decimal(2)))
    weak = after(flats(3), BULL_PAIR)
    (p,) = feed(weak, patterns=("bullish_engulfing",), filters=volume)
    assert p.intent == Intent.NO_TRADE and p.reasons == ("filter_failed:volume",)
    strong = weak[:-1] + [bar(*BULL_PAIR[1], i=4, volume=3000)]
    (p,) = feed(strong, patterns=("bullish_engulfing",), filters=volume)
    assert p.intent == Intent.LONG
    short_history = after(flats(2), BULL_PAIR)
    (p,) = feed(short_history, patterns=("bullish_engulfing",), filters=volume)
    assert p.reasons == ("filter_warmup:volume",)
    (p,) = feed(weak, patterns=("bullish_engulfing",))  # disabled filter adds no condition
    assert p.intent == Intent.LONG


FIVE_DOWN = [
    ("10.0", "10.0", "9.8", "9.8"),
    ("9.8", "9.8", "9.6", "9.6"),
    ("9.6", "9.6", "9.4", "9.4"),
    ("9.4", "9.4", "9.2", "9.2"),
    ("9.2", "9.2", "9.0", "9.0"),
]
FIVE_UP = [
    ("9.0", "9.24", "9.0", "9.24"),
    ("9.24", "9.48", "9.24", "9.48"),
    ("9.48", "9.72", "9.48", "9.72"),
    ("9.72", "9.96", "9.72", "9.96"),
    ("9.96", "10.2", "9.96", "10.2"),
]


def test_higher_timeframes_signal_only_when_the_bucket_is_complete() -> None:
    candles = after([], FIVE_DOWN + FIVE_UP)
    (p,) = feed(candles, patterns=("bullish_engulfing",), timeframes=(5,))
    assert p.intent == Intent.LONG and p.rationale == "bullish_engulfing@5m"
    assert p.generated_at == candles[-1].available  # not before the 10th minute is usable
    assert feed(candles[:9], patterns=("bullish_engulfing",), timeframes=(5,)) == []
    # the same series read at 1m has its own engulfing, earlier (candle 5 completes it)
    (early,) = feed(candles, patterns=("bullish_engulfing",), timeframes=(1,))
    assert early.generated_at == candles[5].available < p.generated_at


def test_proposals_do_not_depend_on_later_candles() -> None:
    candles = after([], FIVE_DOWN + FIVE_UP)
    future = [bar("50", "90", "40", "80", i=10 + j) for j in range(5)]
    kw = {"patterns": ("bullish_engulfing", "bearish_engulfing"), "timeframes": (1, 5)}
    assert feed(candles, **kw) == feed(candles + future, **kw)[: len(feed(candles, **kw))]
    assert feed(candles, **kw) == feed(candles, **kw)  # replay-identical


def test_policy_configuration_is_validated() -> None:
    for bad in (
        {"patterns": ()},
        {"patterns": ("moon",)},
        {"patterns": ("hammer", "hammer")},
        {"patterns": ("hammer",), "timeframes": (7,)},
        {"patterns": ("hammer",), "timeframes": (5, 5)},
        {"patterns": ("hammer",), "neutral_confirm_candles": 0},
        {"patterns": ("hammer",), "horizon_seconds": 0},
        {"patterns": ("hammer",), "allow_long": False, "allow_short": False},
        {"patterns": ("hammer",), "entry_valid_seconds": 0},
    ):
        with pytest.raises(DataError):
            CandlestickParams(**bad)  # type: ignore[arg-type]
    a = CandlestickParams(patterns=("hammer",))
    assert a.version_hash() != CandlestickParams(patterns=("doji",)).version_hash()
