"""SessionTape: causal per-session state shared by the rule models (VWAP, history, ATR)."""

from fractions import Fraction

import pytest
from helpers import DAY, WEEK, bar, calendar_of, day_candles

from quantlab.data.model import DataError
from quantlab.strategies.rule.statistical.session import SessionTape, check_clock


def test_vwap_and_dispersion_match_exact_fractions() -> None:
    tape = SessionTape(calendar_of(DAY))
    rows = [
        ("100", "102", "98", "101", 10),
        ("101", "103", "99", "100", 30),
        ("100", "104", "98", "103", 20),
    ]
    assert tape.vwap is None and tape.vwap_std is None
    for i, (o, h, low, c, v) in enumerate(rows):
        tape.push(bar(o, h, low, c, i=i, volume=v))
    typical = [Fraction(int(h) + int(low) + int(c), 3) for _, h, low, c, _ in rows]
    volume = [Fraction(r[4]) for r in rows]
    vwap = sum(t * v for t, v in zip(typical, volume, strict=True)) / sum(volume)
    var = sum(v * (t - vwap) ** 2 for t, v in zip(typical, volume, strict=True)) / sum(volume)
    assert tape.vwap is not None and tape.vwap_std is not None
    assert abs(Fraction(tape.vwap) - vwap) < Fraction(1, 10**20)
    assert abs(float(tape.vwap_std) - float(var) ** 0.5) < 1e-12


def test_zero_volume_sessions_have_no_vwap_and_flat_prices_have_zero_dispersion() -> None:
    tape = SessionTape(calendar_of(DAY))
    tape.push(bar("100", "100", "100", "100", volume=0))
    assert tape.vwap is None and tape.vwap_std is None
    tape.push(bar("100", "100", "100", "100", i=1, volume=5))
    assert tape.vwap == 100 and tape.vwap_std == 0


def test_push_reports_new_sessions_and_enforces_order_and_calendar() -> None:
    tape = SessionTape(calendar_of(*WEEK[:2]))
    first, second = day_candles(WEEK[0])[:2], day_candles(WEEK[1])[:1]
    assert [tape.push(c) for c in first] == [True, False]
    assert tape.push(second[0]) is True and tape.session is not None
    assert tape.session.day == WEEK[1] and len(tape.today) == 1
    with pytest.raises(DataError, match="ordered"):
        tape.push(first[0])
    with pytest.raises(DataError, match="classified"):
        SessionTape(calendar_of(WEEK[1])).push(first[0])


def test_gaps_clear_the_clean_flag_for_the_session_only() -> None:
    tape = SessionTape(calendar_of(*WEEK[:2]))
    minutes = day_candles(WEEK[0])
    for c in minutes[:3]:
        tape.push(c)
    assert tape.clean
    tape.push(minutes[4])  # minute 3 is missing
    assert not tape.clean
    tape.push(day_candles(WEEK[1])[0])
    assert tape.clean  # a new session starts clean
    late = SessionTape(calendar_of(WEEK[0]))
    late.push(minutes[1])  # the first minute of the session is missing
    assert not late.clean


def test_ended_sessions_become_history_only_when_the_next_one_starts() -> None:
    tape = SessionTape(calendar_of(*WEEK[:4], early=(WEEK[2],)))
    full = day_candles(WEEK[0], at={"12:00": ("100.00", "103.00", "99.00", "100.00")})
    for c in full:
        tape.push(c)
    assert len(tape.days) == 0  # today is not history yet
    tape.push(day_candles(WEEK[1])[0])
    (day,) = tape.days
    assert (day.high, day.low, day.close, day.complete) == (103, 99, 100, True)
    assert day.volume == 390 * 1000
    for c in day_candles(WEEK[1])[1:]:
        tape.push(c)
    for c in day_candles(WEEK[2], "13:00"):
        tape.push(c)
    tape.push(day_candles(WEEK[3])[0])
    # the early-close session is history too, but never "complete" for ATR purposes
    assert [d.complete for d in tape.days] == [True, True, False]


def test_true_range_and_atr_use_only_completed_prior_sessions() -> None:
    days = WEEK[:4]
    tape = SessionTape(calendar_of(*days))
    d1 = day_candles(days[0])
    d2 = day_candles(days[1], at={"12:00": ("100.00", "103.00", "99.00", "100.00")})
    d3 = day_candles(
        days[2], default="102.00", at={"12:00": ("102.00", "102.50", "101.50", "102.00")}
    )
    for c in [*d1, *d2, *d3]:
        tape.push(c)
    assert tape.true_ranges(2) is None  # the third session has not ended yet
    tape.push(day_candles(days[3])[0])
    # D2: range 4 against previous close 100 -> 4; D3: high 102.5 vs previous close 100 -> 2.5
    assert tape.true_ranges(2) == [4, 2.5]
    assert tape.prior_true_range_vs_atr(2) == (2.5, 3.25)
    assert tape.true_ranges(3) is None  # needs n + 1 ended sessions


def test_incomplete_history_is_never_used_for_atr() -> None:
    days = WEEK[:4]
    tape = SessionTape(calendar_of(*days))
    broken = [c for c in day_candles(days[1]) if c.end != day_candles(days[1])[100].end]
    for c in [*day_candles(days[0]), *broken, *day_candles(days[2]), *day_candles(days[3])[:1]]:
        tape.push(c)
    assert tape.prior_true_range_vs_atr(2) is None


def test_clock_validation() -> None:
    assert check_clock("11:30") == "11:30"
    for bad in ("9:30", "09:30", "16:00", "10:75", "noon", "08:00"):
        with pytest.raises(DataError):
            check_clock(bad)
