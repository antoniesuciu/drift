"""CANDLE-001/-002/-003/-005: hand-specified fixtures for every detection, aggregation, filters."""

from dataclasses import replace
from decimal import Decimal

import pytest
from helpers import DAY, bar, day_candles

from quantlab.data.model import SECOND, DataError
from quantlab.strategies.calendar import Calendar, SessionSpec
from quantlab.strategies.market import Aggregator, Candle
from quantlab.strategies.rule.candlestick.filters import (
    Filters,
    LevelFilter,
    TrendFilter,
    VolatilityFilter,
    VolumeFilter,
    evaluate_filters,
)
from quantlab.strategies.rule.candlestick.patterns import PATTERNS, DetectorConfig, detect

CFG = DetectorConfig()
STRICT = DetectorConfig(inclusive=False)


def found(window: list[Candle], name: str, config: DetectorConfig = CFG) -> bool:
    return any(d.pattern == name for d in detect(config, window, [name]))


def seq(*rows: tuple[str, str, str, str]) -> list[Candle]:
    return [bar(*r, i=i) for i, r in enumerate(rows)]


def test_catalogue_has_exactly_the_ten_specified_detections() -> None:
    assert set(PATTERNS) == {
        "bullish_engulfing",
        "bearish_engulfing",
        "hammer",
        "shooting_star",
        "morning_star",
        "evening_star",
        "doji",
        "three_white_soldiers",
        "three_black_crows",
        "inside_bar",
    }
    assert {name: PATTERNS[name][1] for name in PATTERNS} == {
        "bullish_engulfing": "long",
        "bearish_engulfing": "short",
        "hammer": "long",
        "shooting_star": "short",
        "morning_star": "long",
        "evening_star": "short",
        "doji": "neutral",
        "three_white_soldiers": "long",
        "three_black_crows": "short",
        "inside_bar": "neutral",
    }


def test_engulfing_both_directions_and_edges() -> None:
    bull = seq(("10.0", "10.1", "8.9", "9.0"), ("8.9", "10.3", "8.8", "10.2"))
    assert found(bull, "bullish_engulfing") and not found(bull, "bearish_engulfing")
    bear = seq(("9.0", "10.1", "8.9", "10.0"), ("10.1", "10.2", "8.8", "8.9"))
    assert found(bear, "bearish_engulfing") and not found(bear, "bullish_engulfing")
    # second body exactly equals the first: engulfs only with inclusive edges
    edge = seq(("10.0", "10.1", "8.9", "9.0"), ("9.0", "10.2", "8.8", "10.0"))
    assert found(edge, "bullish_engulfing") and not found(edge, "bullish_engulfing", STRICT)
    inside = seq(("10.0", "10.1", "8.9", "9.0"), ("9.1", "10.3", "8.8", "10.2"))
    assert not found(inside, "bullish_engulfing")
    same_color = seq(("10.0", "10.1", "8.9", "9.0"), ("8.9", "10.3", "8.4", "8.5"))
    assert not found(same_color, "bullish_engulfing")


def test_hammer_and_shooting_star_boundaries() -> None:
    hammer = seq(("10.00", "10.25", "9.00", "10.20"))
    assert found(hammer, "hammer") and not found(hammer, "shooting_star")
    # every threshold exactly on its boundary: body/range 0.30, wick = 2 x body, opposite 0.10
    edge = seq(("9.60", "10.00", "9.00", "9.90"))
    assert found(edge, "hammer") and not found(edge, "hammer", STRICT)
    star = seq(("9.40", "10.00", "9.00", "9.10"))
    assert found(star, "shooting_star") and not found(star, "shooting_star", STRICT)
    assert not found(star, "hammer")
    assert not found(seq(("10.00", "10.60", "9.00", "10.20")), "hammer")  # long upper wick
    assert not found(seq(("10.00", "10.00", "9.00", "10.00")), "hammer")  # zero body
    bearish = seq(("10.20", "10.25", "9.00", "10.00"))
    assert found(bearish, "hammer")
    assert not found(bearish, "hammer", DetectorConfig(single_color="bullish"))


def test_stars_penetration_gap_and_degenerate_middle() -> None:
    morning = seq(
        ("10.0", "10.05", "8.95", "9.0"),
        ("8.9", "9.0", "8.8", "8.95"),
        ("8.95", "9.65", "8.9", "9.6"),
    )
    assert found(morning, "morning_star") and not found(morning, "evening_star")
    assert found(morning, "morning_star", DetectorConfig(require_gap=True))
    exact = seq(
        ("10.0", "10.05", "8.95", "9.0"),
        ("8.9", "9.0", "8.8", "8.95"),
        ("8.95", "9.60", "8.9", "9.50"),
    )
    assert found(exact, "morning_star") and not found(exact, "morning_star", STRICT)
    shallow = seq(
        ("10.0", "10.05", "8.95", "9.0"),
        ("8.9", "9.0", "8.8", "8.95"),
        ("8.95", "9.45", "8.9", "9.40"),
    )
    assert not found(shallow, "morning_star")
    no_gap = seq(
        ("10.0", "10.05", "8.95", "9.0"),
        ("9.0", "9.1", "8.9", "9.05"),
        ("9.0", "9.65", "8.9", "9.6"),
    )
    assert found(no_gap, "morning_star")
    assert not found(no_gap, "morning_star", DetectorConfig(require_gap=True))
    flat_middle = seq(
        ("10.0", "10.05", "8.95", "9.0"),
        ("8.9", "8.9", "8.9", "8.9"),
        ("8.95", "9.65", "8.9", "9.6"),
    )
    assert not found(flat_middle, "morning_star")  # zero range: ratio detection withheld
    evening = seq(
        ("9.0", "10.05", "8.95", "10.0"),
        ("10.1", "10.2", "10.0", "10.05"),
        ("10.0", "10.05", "9.35", "9.4"),
    )
    assert found(evening, "evening_star") and not found(evening, "morning_star")


def test_doji_inside_bar_and_degenerate_candles() -> None:
    assert found(seq(("10.00", "10.50", "9.50", "10.02")), "doji")
    assert found(seq(("10.00", "10.50", "9.50", "10.10")), "doji")  # body/range exactly 0.10
    assert not found(seq(("10.00", "10.50", "9.50", "10.10")), "doji", STRICT)
    assert not found(seq(("10.00", "10.50", "9.50", "10.20")), "doji")
    assert not found(seq(("10.00", "10.00", "10.00", "10.00")), "doji")  # degenerate, not doji
    mother = ("10.0", "10.5", "9.5", "10.0")
    assert found(seq(mother, ("10.0", "10.2", "9.8", "10.1")), "inside_bar")
    assert found(seq(mother, ("10.0", "10.5", "9.5", "10.1")), "inside_bar")
    assert not found(seq(mother, ("10.0", "10.5", "9.5", "10.1")), "inside_bar", STRICT)
    assert not found(seq(mother, ("10.0", "10.6", "9.8", "10.1")), "inside_bar")


def test_three_soldiers_and_crows() -> None:
    soldiers = seq(
        ("10.0", "11.1", "9.95", "11.0"),
        ("10.5", "12.1", "10.45", "12.0"),
        ("11.5", "13.1", "11.45", "13.0"),
    )
    assert found(soldiers, "three_white_soldiers") and not found(soldiers, "three_black_crows")
    gapped = seq(
        ("10.0", "11.1", "9.95", "11.0"),
        ("10.5", "12.1", "10.45", "12.0"),
        ("12.2", "13.1", "12.15", "13.0"),
    )
    assert not found(gapped, "three_white_soldiers")  # third open outside the second body
    stalled = seq(
        ("10.0", "11.1", "9.95", "11.0"),
        ("10.5", "12.1", "10.45", "12.0"),
        ("11.5", "12.2", "11.45", "12.0"),
    )
    assert not found(stalled, "three_white_soldiers")  # close not strictly higher
    crows = seq(
        ("13.0", "13.05", "11.9", "12.0"),
        ("12.5", "12.55", "10.9", "11.0"),
        ("11.5", "11.55", "9.9", "10.0"),
    )
    assert found(crows, "three_black_crows") and not found(crows, "three_white_soldiers")


def test_windows_must_be_contiguous_and_within_a_session() -> None:
    first, second = seq(("10.0", "10.1", "8.9", "9.0"), ("8.9", "10.3", "8.8", "10.2"))
    shift = 60 * SECOND
    gap = replace(
        second,
        start=second.start + shift,
        end=second.end + shift,
        available=second.available + shift,
    )
    assert not found([first, gap], "bullish_engulfing")
    other_day = replace(second, day="2022-03-09")
    assert not found([first, other_day], "bullish_engulfing")
    assert detect(CFG, [first, other_day], ["bullish_engulfing"], span_sessions=True)


def test_detection_carries_availability_and_provenance() -> None:
    a, b = seq(("10.0", "10.1", "8.9", "9.0"), ("8.9", "10.3", "8.8", "10.2"))
    late = replace(b, available=b.available + 5 * SECOND)
    (d,) = detect(CFG, [a, late], ["bullish_engulfing"])
    assert d.available == late.available and d.start == a.start and d.end == b.end
    assert d.params_hash == CFG.params_hash() and d.version == "CAND-DET-v1"
    assert detect(CFG, [a, b], ["bullish_engulfing"]) == detect(CFG, [a, b], ["bullish_engulfing"])


def test_prefix_detection_is_independent_of_later_candles() -> None:
    rows = [("10.0", "10.1", "8.9", "9.0"), ("8.9", "10.3", "8.8", "10.2")]
    candles = seq(*rows, ("10.2", "10.4", "10.1", "10.3"), ("5.0", "9.0", "4.0", "8.0"))
    names = list(PATTERNS)
    before = detect(CFG, candles[:2], names)
    assert before == detect(CFG, candles[:2], names)  # pure
    # appending any future candle cannot change an earlier-ending detection
    assert [d for d in detect(CFG, candles[:3], names) if d.end == candles[1].end] == []
    assert before and before[0].end == candles[1].end


def test_detector_configuration_is_validated() -> None:
    for bad in (
        {"doji_max_body_ratio": Decimal("1.5")},
        {"star_penetration": Decimal(0)},
        {"wick_min_body_multiple": Decimal(0)},
        {"single_color": "blue"},
        {"small_body_max_ratio": Decimal("0.7")},
    ):
        with pytest.raises(DataError):
            DetectorConfig(**bad)
    with pytest.raises(DataError, match="unknown detection id"):
        detect(CFG, [bar("1", "2", "1", "2")], ["moon"])
    assert DetectorConfig().params_hash() != DetectorConfig(inclusive=False).params_hash()


def test_invalid_candles_are_rejected() -> None:
    with pytest.raises(DataError, match="OHLC"):
        bar("10", "9", "8", "9.5")
    with pytest.raises(DataError, match="OHLC"):
        bar("10", "11", "0", "10")
    good = bar("10", "11", "9", "10")
    with pytest.raises(DataError, match="timing"):
        replace(good, available=good.end - 1)


def test_aggregation_timeframes_ohlcv_and_availability() -> None:
    minutes = day_candles(DAY, at={})
    ramp = [
        replace(
            m,
            open=Decimal(100) + i,
            high=Decimal(102) + i,
            low=Decimal(99) + i,
            close=Decimal(101) + i,
            volume=10,
        )
        for i, m in enumerate(minutes)
    ]
    calendar = Calendar((SessionSpec(DAY),))
    for tf, expected in ((1, 390), (5, 78), (15, 26), (30, 13), (60, 6)):
        agg, out = Aggregator(tf, calendar), []
        for m in ramp:
            k = agg.push(m)
            if k is not None:
                out.append(k)
        assert len(out) == expected  # the truncated 15:30-16:00 hour is never published
        assert agg.incomplete == 0
    agg = Aggregator(5, calendar)
    built = [k for m in ramp if (k := agg.push(m)) is not None][0]
    assert (built.open, built.high, built.low, built.close, built.volume) == (
        Decimal(100),
        Decimal(106),
        Decimal(99),
        Decimal(105),
        50,
    )
    assert built.available == ramp[4].available and built.end == ramp[4].end


def test_aggregation_waits_for_a_delayed_last_component_and_skips_gaps() -> None:
    calendar = Calendar((SessionSpec(DAY),))
    minutes = day_candles(DAY)[:10]
    agg = Aggregator(5, calendar)
    late = replace(minutes[4], available=minutes[4].available + 30 * SECOND)
    emitted = [agg.push(m) for m in (*minutes[:4], late)]
    assert emitted[:4] == [None] * 4 and emitted[4] is not None
    assert emitted[4].available == late.available
    agg = Aggregator(5, calendar)
    emitted = [agg.push(m) for m in minutes if m is not minutes[2]]
    # the bucket missing a minute is never published; the next one is unaffected
    assert [e is not None for e in emitted] == [False] * 8 + [True]
    assert agg.incomplete == 1


def test_aggregation_rejects_disorder_and_unclassified_sessions() -> None:
    minutes = day_candles(DAY)[:3]
    agg = Aggregator(5, Calendar((SessionSpec(DAY),)))
    agg.push(minutes[1])
    with pytest.raises(DataError, match="ordered"):
        agg.push(minutes[0])
    with pytest.raises(DataError, match="classified"):
        Aggregator(5, Calendar((SessionSpec("2022-03-09"),))).push(minutes[0])
    with pytest.raises(DataError, match="timeframe"):
        Aggregator(7, Calendar((SessionSpec(DAY),)))


def history(n: int) -> list[Candle]:
    return [bar(str(100 + i), str(101 + i), str(99 + i), str(100 + i), i=i) for i in range(n)]


def test_filters_pass_fail_and_warm_up_independently() -> None:
    tick = Decimal("0.01")
    pattern = [bar("100", "101", "98", "100.5", i=10, volume=4000)]
    falling = [bar(str(120 - i), str(121 - i), str(119 - i), str(120 - i), i=i) for i in range(6)]
    off = Filters()
    assert evaluate_filters(off, "long", pattern, falling, tick) is None  # disabled adds nothing
    trend = Filters(trend=TrendFilter(5))
    assert (
        evaluate_filters(trend, "long", pattern, falling, tick) is None
    )  # downtrend, long reversal
    assert evaluate_filters(trend, "short", pattern, falling, tick) == "filter_failed:trend"
    assert evaluate_filters(trend, "long", pattern, falling[:3], tick) == "filter_warmup:trend"
    level = Filters(level=LevelFilter(5, 0))
    assert evaluate_filters(level, "long", pattern, falling, tick) is None  # low 98 <= min low
    assert evaluate_filters(Filters(level=LevelFilter(5, 0)), "short", pattern, falling, tick) == (
        "filter_failed:level"
    )
    volume = Filters(volume=VolumeFilter(5, Decimal("2")))
    assert evaluate_filters(volume, "long", pattern, falling, tick) is None  # 4000 >= 2 x 1000
    weak = [bar("100", "101", "98", "100.5", i=10, volume=1500)]
    assert evaluate_filters(volume, "long", weak, falling, tick) == "filter_failed:volume"
    empty = [replace(falling[-1], volume=0)]
    assert evaluate_filters(volume, "long", pattern, [*falling[:-1], *empty], tick) == (
        "filter_unavailable:volume"
    )
    vol = Filters(volatility=VolatilityFilter(5, Decimal(150), Decimal(300)))
    assert evaluate_filters(vol, "long", pattern, falling, tick) is None  # ATR 2.0 = 200 ticks
    tight = Filters(volatility=VolatilityFilter(5, Decimal(250), None))
    assert evaluate_filters(tight, "long", pattern, falling, tick) == "filter_failed:volatility"
    assert evaluate_filters(vol, "long", pattern, falling[:3], tick) == "filter_warmup:volatility"


def test_filter_configuration_is_validated() -> None:
    for bad in (
        lambda: Filters(trend=TrendFilter(0)),
        lambda: Filters(trend=TrendFilter(3, long_requires="sideways")),
        lambda: Filters(volume=VolumeFilter(3, Decimal(0))),
        lambda: Filters(level=LevelFilter(3, -1)),
    ):
        with pytest.raises(DataError):
            bad()
