"""Mean reversion: shared band-fade core plus the VWAP and Bollinger variants."""

from decimal import Decimal
from fractions import Fraction

import pytest
from helpers import DAY, bar, calendar_of, feed_all, walk

from quantlab.data.model import NY, DataError, instant
from quantlab.strategies.market import Candle
from quantlab.strategies.proposal import Intent
from quantlab.strategies.rule.statistical.bollinger_reversion import (
    BollingerParams,
    BollingerReversionRule,
)
from quantlab.strategies.rule.statistical.fade import FadeParams
from quantlab.strategies.rule.statistical.vwap_reversion import VwapParams, VwapReversionRule

WIDE = {"window_start": "09:31", "window_end": "14:00"}


def flat(closes: list[str], day: str = DAY) -> list[Candle]:
    return [bar(c, c, c, c, i=i, day=day) for i, c in enumerate(closes)]


def boll(closes: list[str], **kw: object) -> list:
    params = BollingerParams(timeframe=1, period=3, sigma_multiple=Decimal(1), **WIDE, **kw)  # type: ignore[arg-type]
    return feed_all(BollingerReversionRule(params, "SYNTH.XNAS", calendar_of(DAY)), flat(closes))


def test_bollinger_stretch_up_is_faded_with_a_hand_checked_reading() -> None:
    # window [100.1, 100.0, ...]: the last window [100.0, 100.1, 101.0] has z = 1.408 >= 1
    # after z = 0 on the previous candle, so exactly one fresh crossing at candle index 4
    candles = flat(["100.0", "100.2", "100.0", "100.1", "101.0"])
    (p,) = boll(["100.0", "100.2", "100.0", "100.1", "101.0"])
    assert p.intent == Intent.SHORT and p.generated_at == candles[4].available
    assert p.rationale.startswith("z=1.41 mid=100.3667") and p.horizon_seconds == 1200
    assert p.reasons == () and p.family == "RULE"


def test_bollinger_stretch_down_goes_long_and_disabled_directions_abstain() -> None:
    (p,) = boll(["100.0", "99.8", "100.0", "99.9", "99.0"])
    assert p.intent == Intent.LONG
    (q,) = boll(["100.0", "99.8", "100.0", "99.9", "99.0"], allow_long=False)
    assert q.intent == Intent.NO_TRADE and q.reasons == ("direction_disabled",)


def test_a_reading_that_stays_outside_the_band_does_not_repeat() -> None:
    # z per candle from index 2: -0.71, 0, +1.41 (SHORT), 0.82, -1.22 (LONG), -1.07 (still
    # outside: no repeat), +1.41 (SHORT). Only fresh crossings trigger.
    closes = ["100.0", "100.2", "100.0", "100.1", "101.0", "101.1", "100.9", "100.8", "102.0"]
    candles = flat(closes)
    got = boll(closes)
    assert [p.intent for p in got] == [Intent.SHORT, Intent.LONG, Intent.SHORT]
    assert [p.generated_at for p in got] == [candles[i].available for i in (4, 6, 8)]


def test_undefined_readings_never_trigger() -> None:
    # zero dispersion (all equal closes) is undefined, and the first defined reading has no prior
    assert boll(["100.0"] * 5) == []
    assert boll(["100.0", "100.0", "100.0", "101.0"]) == []


def test_signals_outside_the_window_are_ignored() -> None:
    params = BollingerParams(
        timeframe=1,
        period=3,
        sigma_multiple=Decimal(1),
        window_start="10:00",
        window_end="14:00",
    )
    rule = BollingerReversionRule(params, "SYNTH.XNAS", calendar_of(DAY))
    assert feed_all(rule, flat(["100.0", "100.2", "100.0", "100.1", "101.0"])) == []


def test_vwap_fade_core_is_edge_triggered_and_window_gated() -> None:
    params = VwapParams(**WIDE, sigma_multiple=Decimal("1.5"), min_bars=3)
    candles = flat(["100.0", "100.2", "99.8", "100.1", "99.9", "100.0", "100.1", "103.0", "103.1"])
    got = feed_all(VwapReversionRule(params, "SYNTH.XNAS", calendar_of(DAY)), candles)
    assert [p.intent for p in got] == [Intent.SHORT]  # the spike fires once, not on 103.1
    assert got[0].generated_at == candles[7].available and "vwap=" in got[0].rationale


# ---- differential tests against an independent exact reference -------------------------


def crossings(zs: list[tuple[int, bool, bool] | None]) -> list[tuple[int, str]]:
    """(index, side) fresh crossings from per-candle (index, z >= k, z <= -k) states."""
    out: list[tuple[int, str]] = []
    prev: tuple[int, bool, bool] | None = None
    for state in zs:
        if state is not None and prev is not None:
            if state[1] and not prev[1]:
                out.append((state[0], "SHORT"))
            elif state[2] and not prev[2]:
                out.append((state[0], "LONG"))
        prev = state
    return out


def state(index: int, dev: Fraction, var: Fraction, k: Fraction) -> tuple[int, bool, bool] | None:
    if var <= 0:
        return None
    ge = dev >= 0 and dev * dev >= k * k * var
    le = dev <= 0 and dev * dev >= k * k * var
    return index, ge, le


def test_vwap_rule_matches_an_exact_reference_over_generated_sessions() -> None:
    data = walk(seed=5, sessions=3, step_ticks=10)
    k = Fraction(3, 2)
    params = VwapParams(sigma_multiple=Decimal("1.5"))
    got = feed_all(VwapReversionRule(params, "SYNTH.XNAS", data.calendar), list(data.candles))
    expected: list[tuple[int, str]] = []
    for day in {c.day for c in data.candles}:
        idx = [i for i, c in enumerate(data.candles) if c.day == day]
        v = pv = pv2 = Fraction(0)
        states: list[tuple[int, bool, bool] | None] = []
        for n, i in enumerate(idx, start=1):
            c = data.candles[i]
            t = Fraction(c.high + c.low + c.close) / 3
            v, pv, pv2 = v + c.volume, pv + c.volume * t, pv2 + c.volume * t * t
            if n < params.min_bars:
                states.append(None)
                continue
            mean = pv / v
            states.append(state(i, Fraction(c.close) - mean, pv2 / v - mean * mean, k))
        expected += [
            (i, s) for i, s in crossings(states) if "11:30" <= _clock(data.candles[i]) <= "14:00"
        ]
    expected.sort()
    seen = sorted((data.candles.index(_candle(data, p)), str(p.intent)) for p in got)
    assert expected and seen == expected


def _clock(c: Candle) -> str:
    return instant(c.end).astimezone(NY).strftime("%H:%M")


def _candle(data, proposal) -> Candle:  # type: ignore[no-untyped-def]
    end = int(proposal.input_refs[1].split(":")[1])
    return next(c for c in data.candles if c.end == end)


def test_bollinger_rule_matches_an_exact_reference_over_generated_sessions() -> None:
    data = walk(seed=9, sessions=3, step_ticks=10)
    k = Fraction(2)
    params = BollingerParams(timeframe=5, period=8, sigma_multiple=Decimal(2))
    got = feed_all(BollingerReversionRule(params, "SYNTH.XNAS", data.calendar), list(data.candles))
    expected: list[tuple[int, str]] = []
    for day in {c.day for c in data.candles}:
        minutes = [(i, c) for i, c in enumerate(data.candles) if c.day == day]
        buckets = [minutes[j : j + 5] for j in range(0, len(minutes) - 4, 5)]
        closes = [Fraction(b[-1][1].close) for b in buckets]
        states: list[tuple[int, bool, bool] | None] = []
        for n, b in enumerate(buckets):
            window = closes[max(0, n - 7) : n + 1]
            if len(window) < 8:
                states.append(None)
                continue
            mean = sum(window) / 8
            var = sum((x - mean) ** 2 for x in window) / 8
            states.append(state(b[-1][0], window[-1] - mean, var, k))
        expected += [
            (i, s) for i, s in crossings(states) if "11:30" <= _clock(data.candles[i]) <= "14:00"
        ]
    expected.sort()
    seen = sorted((data.candles.index(_candle(data, p)), str(p.intent)) for p in got)
    assert expected and seen == expected


def test_parameter_validation() -> None:
    for bad in (
        {"window_start": "14:00", "window_end": "11:30"},
        {"window_start": "09:30"},
        {"sigma_multiple": Decimal(0)},
        {"horizon_seconds": 0},
        {"entry_valid_seconds": 0},
        {"allow_long": False, "allow_short": False},
    ):
        with pytest.raises(DataError):
            FadeParams(**bad)
    with pytest.raises(DataError):
        VwapParams(min_bars=1)
    for bad_boll in ({"timeframe": 7}, {"period": 1}):
        with pytest.raises(DataError):
            BollingerParams(**bad_boll)
