"""Short-term reversal and moving-average trend following."""

from decimal import Decimal
from fractions import Fraction

import pytest
from helpers import DAY, calendar_of, day_candles, feed_all, walk

from quantlab.data.model import SECOND, DataError, local_ns
from quantlab.strategies.proposal import Intent
from quantlab.strategies.rule.statistical.reversal import ReversalParams, ReversalRule
from quantlab.strategies.rule.statistical.trend import TrendParams, TrendRule

DOWN15 = {"09:45": ("100.00", "100.00", "99.00", "99.00")}  # first 15m: 100.00 -> 99.00 (-1%)
UP15 = {"09:45": ("100.00", "101.00", "100.00", "101.00")}  # +1%


def reversal(at: dict, **params: object) -> list:
    rule = ReversalRule(ReversalParams(**params), "SYNTH.XNAS", calendar_of(DAY))  # type: ignore[arg-type]
    return feed_all(rule, day_candles(DAY, at=at))


def test_a_falling_bucket_is_bought_and_a_rising_one_is_sold() -> None:
    (p,) = reversal(DOWN15)
    assert p.intent == Intent.LONG and p.horizon_seconds == 900 and p.reasons == ()
    assert (
        p.generated_at == local_ns(DAY, "09:45") + SECOND and p.rationale == "15m_return=-0.010000"
    )
    (q,) = reversal(UP15)
    assert q.intent == Intent.SHORT and q.rationale == "15m_return=0.010000"


def test_flat_buckets_and_sub_threshold_moves_do_not_signal() -> None:
    assert reversal({}) == []
    assert reversal(DOWN15, min_abs_return_bps=Decimal(150)) == []  # 100 bps < 150
    assert reversal(DOWN15, min_abs_return_bps=Decimal(100))[0].intent == Intent.LONG  # equality
    assert reversal(DOWN15, min_abs_return_bps=Decimal(50))[0].intent == Intent.LONG


def test_long_flat_control_abstains_on_the_short_side() -> None:
    (p,) = reversal(UP15, allow_short=False)
    assert p.intent == Intent.NO_TRADE and p.reasons == ("direction_disabled",)
    assert reversal(DOWN15, allow_short=False)[0].intent == Intent.LONG


def test_other_timeframes_and_gaps() -> None:
    (p,) = reversal({"09:35": ("100.00", "100.00", "99.50", "99.50")}, timeframe=5)
    assert p.intent == Intent.LONG and p.generated_at == local_ns(DAY, "09:35") + SECOND
    rule = ReversalRule(ReversalParams(), "SYNTH.XNAS", calendar_of(DAY))
    gap = [c for c in day_candles(DAY, at=DOWN15) if c.end != local_ns(DAY, "09:40")]
    assert feed_all(rule, gap) == []  # a bucket with a missing minute is never evaluated


def test_reversal_matches_an_exact_reference_over_generated_sessions() -> None:
    data = walk(seed=4, sessions=3, step_ticks=8)
    min_bps = Fraction(20)
    params = ReversalParams(min_abs_return_bps=Decimal(20))
    got = feed_all(ReversalRule(params, "SYNTH.XNAS", data.calendar), list(data.candles))
    expected = []
    for day in sorted({c.day for c in data.candles}):
        minutes = [c for c in data.candles if c.day == day]
        for j in range(0, len(minutes), 15):
            block = minutes[j : j + 15]
            if len(block) < 15:
                continue
            o, c = Fraction(block[0].open), Fraction(block[-1].close)
            if c != o and abs(c - o) * 10_000 >= min_bps * o:
                expected.append((block[-1].end, Intent.LONG if c < o else Intent.SHORT))
    seen = [(int(p.input_refs[1].split(":")[1]), p.intent) for p in got]
    assert expected and seen == expected


def test_reversal_parameter_validation() -> None:
    for bad in (
        {"timeframe": 7},
        {"min_abs_return_bps": Decimal(-1)},
        {"horizon_seconds": 0},
        {"entry_valid_seconds": 0},
        {"allow_long": False, "allow_short": False},
    ):
        with pytest.raises(DataError):
            ReversalParams(**bad)


def bucket_closes(closes: dict[int, str]) -> dict[str, tuple[str, str, str, str]]:
    """Set the close of 5-minute bucket n (1-based) by setting its last minute's candle."""
    out = {}
    for n, value in closes.items():
        total = 9 * 60 + 30 + 5 * n
        flat = ("100.00", max("100.00", value), min("100.00", value), value)
        out[f"{total // 60:02d}:{total % 60:02d}"] = flat
    return out


def trend(at: dict, **params: object) -> list:
    rule = TrendRule(
        TrendParams(timeframe=5, fast=2, slow=4, **params), "SYNTH.XNAS", calendar_of(DAY)
    )  # type: ignore[arg-type]
    return feed_all(rule, day_candles(DAY, at=at))


def test_fast_crossing_the_slow_average_is_a_signal_both_ways() -> None:
    # bucket closes: 100 x5, 101, then back to 100 forever
    got = trend(bucket_closes({6: "101.00"}))
    assert [p.intent for p in got] == [Intent.LONG, Intent.SHORT]
    # bucket 6 ends 10:00: sma2 = 100.5 crosses above sma4 = 100.25; bucket 8 (10:10) crosses back
    assert [p.generated_at for p in got] == [local_ns(DAY, t) + SECOND for t in ("10:00", "10:10")]
    assert got[0].rationale == "sma2=100.5000 sma4=100.2500"
    assert got[1].rationale == "sma2=100.0000 sma4=100.2500"
    assert got[0].horizon_seconds == (local_ns(DAY, "16:00") - got[0].generated_at) // SECOND


def test_no_signal_without_a_fresh_cross_or_enough_history() -> None:
    assert trend({}) == []  # equal averages never cross
    # a spike at bucket 4 would cross up, but only 4 closes exist (slow + 1 = 5 are needed), so
    # that cross is never evaluated; the genuine cross back down at bucket 6 (10:00) still fires
    (p,) = trend(bucket_closes({4: "101.00"}))
    assert p.intent == Intent.SHORT and p.generated_at == local_ns(DAY, "10:00") + SECOND


def test_disabled_trend_direction_only_requests_flat() -> None:
    got = trend(bucket_closes({6: "101.00"}), allow_long=False)
    assert got[0].intent == Intent.FLAT and got[0].reasons == ("direction_disabled",)
    assert got[1].intent == Intent.SHORT


def test_trend_matches_an_exact_reference_over_generated_sessions() -> None:
    data = walk(seed=2, sessions=3, step_ticks=6, gap_ticks=60)
    fast, slow = 3, 6
    params = TrendParams(timeframe=5, fast=fast, slow=slow)
    got = feed_all(TrendRule(params, "SYNTH.XNAS", data.calendar), list(data.candles))
    expected = []
    for day in sorted({c.day for c in data.candles}):
        minutes = [c for c in data.candles if c.day == day]
        buckets = [minutes[j : j + 5] for j in range(0, len(minutes) - 4, 5)]
        closes = [Fraction(b[-1].close) for b in buckets]

        def sma(n: int, end: int, closes: list[Fraction] = closes) -> Fraction:
            return sum(closes[end - n : end]) / n

        for i in range(slow, len(closes)):  # index i needs slow + 1 closes: closes[:i + 1]
            f, s = sma(fast, i + 1), sma(slow, i + 1)
            fp, sp = sma(fast, i), sma(slow, i)
            if fp <= sp and f > s:
                expected.append((buckets[i][-1].end, Intent.LONG))
            elif fp >= sp and f < s:
                expected.append((buckets[i][-1].end, Intent.SHORT))
    seen = [(int(p.input_refs[1].split(":")[1]), p.intent) for p in got]
    assert expected and seen == expected


def test_trend_parameter_validation() -> None:
    for bad in (
        {"timeframe": 7},
        {"fast": 0},
        {"fast": 5, "slow": 5},
        {"fast": 6, "slow": 3},
        {"entry_valid_seconds": 0},
        {"allow_long": False, "allow_short": False},
    ):
        with pytest.raises(DataError):
            TrendParams(**bad)
