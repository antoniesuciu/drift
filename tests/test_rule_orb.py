"""Opening range breakout: range, window, one-signal rule, filters, abstentions, causality."""

from dataclasses import replace
from decimal import Decimal
from typing import Any

import pytest
from helpers import WEEK, calendar_of, day_candles, feed_all

from drift.data.model import SECOND, DataError, local_ns
from drift.strategies.calendar import Calendar
from drift.strategies.market import Candle
from drift.strategies.proposal import Intent, Proposal
from drift.strategies.rule.statistical.orb import OrbParams, OrbRule

D = WEEK[1]
RANGE = {"09:40": ("100.00", "101.00", "99.00", "100.00")}  # opening range 99.00-101.00
UP = {"09:50": ("100.00", "101.60", "100.00", "101.50")}
DOWN = {"09:50": ("100.00", "100.00", "98.40", "98.50")}


def run(
    sessions: list[tuple[str, dict[str, Any]]],
    calendar: Calendar | None = None,
    or_volume: dict[str, int] | None = None,
    **params: Any,
) -> dict[str, list[Proposal]]:
    """Proposals by session day for [(day, `at` overrides)] with optional opening volumes."""
    rule = OrbRule(
        OrbParams(**params), "SYNTH.XNAS", calendar or calendar_of(*(d for d, _ in sessions))
    )
    out: dict[str, list[Proposal]] = {}
    for day, at in sessions:
        candles = day_candles(day, at=at)
        if or_volume and day in or_volume:
            candles = [
                replace(c, volume=or_volume[day]) if i < 15 else c for i, c in enumerate(candles)
            ]
        out[day] = feed_all(rule, candles)
    return out


def one(proposals: dict[str, list[Proposal]], day: str = D) -> Proposal:
    (p,) = proposals[day]
    return p


def test_close_above_the_range_goes_long_at_the_breakout_candle() -> None:
    later = {"09:55": ("101.50", "102.50", "101.50", "102.00")}  # a second breakout is ignored
    p = one(run([(D, RANGE | UP | later)]))
    assert p.intent == Intent.LONG and p.reasons == () and p.family == "RULE"
    assert p.generated_at == p.data_asof == local_ns(D, "09:50") + SECOND
    assert "above range 99.00-101.00" in p.rationale and p.horizon_seconds == 1800
    assert p.valid_until == p.generated_at + 300 * SECOND


def test_close_below_the_range_goes_short() -> None:
    p = one(run([(D, RANGE | DOWN)]))
    assert p.intent == Intent.SHORT and "below range" in p.rationale


def test_the_breakout_must_close_strictly_beyond_the_range() -> None:
    touch = {"09:50": ("100.00", "101.00", "100.00", "101.00")}  # close equals the high
    p = one(run([(D, RANGE | touch)]))
    assert p.intent == Intent.NO_TRADE and p.reasons == ("no_breakout",)
    assert p.generated_at == local_ns(D, "11:00") + SECOND  # abstains at the cutoff candle


def test_only_breakouts_inside_the_window_count() -> None:
    late = {"11:05": ("100.00", "103.00", "100.00", "102.50")}
    p = one(run([(D, RANGE | late)]))
    assert p.intent == Intent.NO_TRADE and p.reasons == ("no_breakout",)
    at_cutoff = {"11:00": ("100.00", "103.00", "100.00", "102.50")}
    p = one(run([(D, RANGE | at_cutoff)]))
    assert p.intent == Intent.LONG and p.generated_at == local_ns(D, "11:00") + SECOND


def test_a_disabled_direction_keeps_scanning_for_the_other_side() -> None:
    both = RANGE | DOWN | {"10:00": ("100.00", "101.80", "100.00", "101.70")}
    p = one(run([(D, both)], allow_short=False))
    assert p.intent == Intent.LONG and p.generated_at == local_ns(D, "10:00") + SECOND
    p = one(run([(D, RANGE | DOWN)], allow_short=False))
    assert p.intent == Intent.NO_TRADE and p.reasons == ("direction_disabled",)


def test_an_incomplete_opening_range_abstains_even_with_a_breakout() -> None:
    rule = OrbRule(OrbParams(), "SYNTH.XNAS", calendar_of(D))
    candles = [c for c in day_candles(D, at=RANGE | UP) if c.end != local_ns(D, "09:35")]
    (p,) = feed_all(rule, candles)
    assert p.intent == Intent.NO_TRADE and p.reasons == ("range_incomplete",)


def test_range_length_is_configurable() -> None:
    short = {
        "09:35": ("100.00", "100.40", "99.60", "100.00"),
        "09:40": ("100.00", "100.50", "100.00", "100.50"),
    }
    p = one(run([(D, short)], range_minutes=5))
    assert p.intent == Intent.LONG and p.generated_at == local_ns(D, "09:40") + SECOND
    long_ = RANGE | UP | {"10:05": ("100.00", "101.80", "100.00", "101.70")}
    p = one(run([(D, long_)], range_minutes=30))  # the 09:50 bar is still inside the 30m range
    assert p.generated_at == local_ns(D, "10:05") + SECOND and p.intent == Intent.LONG


def test_relative_volume_filter_warms_up_then_compares_with_prior_sessions() -> None:
    days = WEEK[:4]
    sessions = [(d, RANGE | UP) for d in days]
    volumes = {days[0]: 1000, days[1]: 1000, days[2]: 2000, days[3]: 1000}
    got = run(sessions, or_volume=volumes, rvol_min=Decimal("1.2"), rvol_lookback=2)
    summary = {d: (one(got, d).intent, one(got, d).reasons) for d in days}
    assert summary[days[0]] == (Intent.NO_TRADE, ("filter_warmup:rvol",))
    assert summary[days[1]] == (Intent.NO_TRADE, ("filter_warmup:rvol",))
    assert summary[days[2]] == (Intent.LONG, ())  # 30,000 vs mean 15,000 = 2.0
    assert summary[days[3]] == (Intent.NO_TRADE, ("filter_failed:rvol",))  # 15,000 vs 22,500


def test_vwap_alignment_requires_the_close_on_the_breakout_side() -> None:
    heavy = {"09:46": ("100.50", "120.00", "100.00", "100.50", 100000)}  # drags VWAP far above
    day = RANGE | heavy | UP
    assert one(run([(D, day)])).intent == Intent.LONG
    p = one(run([(D, day)], vwap_alignment=True))
    assert p.intent == Intent.NO_TRADE and p.reasons == ("filter_failed:vwap",)
    assert one(run([(D, RANGE | DOWN)], vwap_alignment=True)).intent == Intent.SHORT


def test_breakout_volume_filter_compares_with_the_ranges_average_bar() -> None:
    weak = {"09:50": ("100.00", "101.60", "100.00", "101.50", 1200)}
    strong = {"09:50": ("100.00", "101.60", "100.00", "101.50", 2000)}
    p = one(run([(D, RANGE | weak)], breakout_volume_multiple=Decimal("1.5")))
    assert p.reasons == ("filter_failed:breakout_volume",)
    p = one(run([(D, RANGE | strong)], breakout_volume_multiple=Decimal("1.5")))
    assert p.intent == Intent.LONG  # 2000 >= 1.5 x 1000


def atr_sessions(d3_extreme: tuple[str, str, str, str]) -> list[tuple[str, dict[str, Any]]]:
    return [
        (WEEK[0], {}),
        (WEEK[1], {"12:00": ("100.00", "102.00", "98.00", "100.00")}),  # range 4 -> TR 4
        (WEEK[2], {"12:00": d3_extreme}),
        (WEEK[3], RANGE | UP),
    ]


def test_prior_true_range_below_atr_filter() -> None:
    calm = ("100.00", "100.50", "99.50", "100.00")  # yesterday TR 1 < ATR 2.5
    wild = ("100.00", "103.00", "97.00", "100.00")  # yesterday TR 6 >= ATR 5
    p = one(run(atr_sessions(calm), prior_tr_below_atr=2), WEEK[3])
    assert p.intent == Intent.LONG
    p = one(run(atr_sessions(wild), prior_tr_below_atr=2), WEEK[3])
    assert p.intent == Intent.NO_TRADE and p.reasons == ("filter_failed:atr",)
    p = one(run(atr_sessions(calm)[1:], prior_tr_below_atr=2), WEEK[3])
    assert p.reasons == ("filter_warmup:atr",)  # only two ended sessions: not enough history


def test_one_decision_per_session_and_replay_is_deterministic() -> None:
    sessions = [(WEEK[0], RANGE | UP), (WEEK[1], RANGE | DOWN), (WEEK[2], {})]
    got = run(sessions)
    assert [len(v) for v in got.values()] == [1, 1, 1]
    assert [one(got, d).intent for d in WEEK[:3]] == [Intent.LONG, Intent.SHORT, Intent.NO_TRADE]
    assert got == run(sessions)


def test_later_candles_cannot_change_an_issued_decision() -> None:
    candles = day_candles(D, at=RANGE | UP)
    cut = next(i for i, c in enumerate(candles) if c.end == local_ns(D, "09:50")) + 1
    wild: list[Candle] = [
        replace(c, open=c.open + 40, high=c.high + 50, low=c.low + 30, close=c.close + 45)
        for c in candles[cut:]
    ]

    def decide(stream: list[Candle]) -> list[Proposal]:
        return feed_all(OrbRule(OrbParams(), "SYNTH.XNAS", calendar_of(D)), stream)

    assert decide(candles[:cut]) == decide(candles)[:1] == decide(candles[:cut] + wild)[:1]
    assert decide(candles[:cut])[0].intent == Intent.LONG


def test_parameter_validation() -> None:
    for bad in (
        {"range_minutes": 10},
        {"entry_cutoff": "09:40"},  # not after a 15-minute range
        {"entry_cutoff": "16:00"},
        {"range_minutes": 30, "entry_cutoff": "10:00"},
        {"rvol_min": Decimal(0)},
        {"rvol_lookback": 0},
        {"breakout_volume_multiple": Decimal(0)},
        {"prior_tr_below_atr": 0},
        {"prior_tr_below_atr": 64},  # beyond the retained sessions: could never warm up
        {"horizon_seconds": 0},
        {"entry_valid_seconds": 0},
        {"allow_long": False, "allow_short": False},
    ):
        with pytest.raises(DataError):
            OrbParams(**bad)
