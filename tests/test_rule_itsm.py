"""EXP-001 ITSM rule (M3a): signal conditions, abstentions, split handling, causality."""

from dataclasses import replace
from decimal import Decimal

import pytest
from helpers import day_candles

from drift.data.model import SECOND, DataError, local_ns
from drift.strategies.calendar import Calendar, SessionSpec
from drift.strategies.market import Candle
from drift.strategies.proposal import Intent, Proposal
from drift.strategies.rule.statistical.itsm import ItsmParams, ItsmRule

D1, D2 = "2022-03-07", "2022-03-08"
UP = {"10:00": "101.00", "15:00": "100.50", "15:30": "101.00"}
DOWN = {"10:00": "99.00", "15:00": "99.50", "15:30": "99.00"}


def run(
    sessions: list[tuple[str, str, dict[str, str]]],
    params: ItsmParams | None = None,
    base: str = "100.00",
) -> list[Proposal]:
    calendar = Calendar(tuple(SessionSpec(d, c) for d, c, _ in sessions))
    rule = ItsmRule(params or ItsmParams(), "SYNTH.XNAS", calendar)
    out = []
    for day, close, at in sessions:
        for candle in day_candles(day, close, base, at):
            proposal = rule.on_candle(candle)
            if proposal is not None:
                out.append(proposal)
    return out


def last(sessions: list[tuple[str, str, dict[str, str]]], **kwargs: object) -> Proposal:
    return run(sessions, **kwargs)[-1]  # type: ignore[arg-type]


def test_both_returns_positive_goes_long_at_the_decision_clock() -> None:
    proposals = run([(D1, "16:00", {}), (D2, "16:00", UP)])
    assert [p.intent for p in proposals] == [Intent.NO_TRADE, Intent.LONG]
    p = proposals[-1]
    decision_end = local_ns(D2, "15:30")
    assert p.generated_at == p.data_asof == decision_end + SECOND  # candle availability
    assert p.valid_until == p.generated_at + 300 * SECOND
    assert p.reasons == () and p.family == "RULE" and p.rule_version == "EXP-001-NVDA-v1"
    assert p.proposal_id == f"EXP-001-ITSM|SYNTH.XNAS|{D2}|{p.generated_at}"
    assert "r_early=0.01" in p.rationale


def test_both_returns_negative_goes_short_unless_disabled() -> None:
    sessions = [(D1, "16:00", {}), (D2, "16:00", DOWN)]
    assert last(sessions).intent == Intent.SHORT
    blocked = last(sessions, params=ItsmParams(allow_short=False))
    assert blocked.intent == Intent.NO_TRADE and blocked.reasons == ("short_disabled",)


def test_disagreement_and_zero_returns_abstain() -> None:
    mixed = {"10:00": "101.00", "15:00": "100.50", "15:30": "100.00"}
    p = last([(D1, "16:00", {}), (D2, "16:00", mixed)])
    assert p.intent == Intent.NO_TRADE and p.reasons == ("zero_or_disagreement",)
    flat = last([(D1, "16:00", {}), (D2, "16:00", {})])
    assert flat.intent == Intent.NO_TRADE and flat.reasons == ("zero_or_disagreement",)


def test_split_neutral_previous_close() -> None:
    # prices on D2 are on the post-split basis (about 100): the 4:1 factor makes early +1%
    sessions = [
        (D1, "16:00", {"16:00": "400.00"}),
        (D2, "16:00", {"10:00": "101.00", "15:00": "100.50", "15:30": "101.00"}),
    ]
    calendar = Calendar(tuple(SessionSpec(d, c) for d, c, _ in sessions))

    def decide(splits: tuple[tuple[str, Decimal], ...]) -> Proposal:
        rule = ItsmRule(ItsmParams(splits=splits), "SYNTH.XNAS", calendar)
        out = []
        for day, close, at in sessions:
            default = "400.00" if day == D1 else "100.00"
            out += [x for c in day_candles(day, close, default, at) if (x := rule.on_candle(c))]
        return out[-1]

    assert decide(((D2, Decimal(4)),)).intent == Intent.LONG  # 101 / (400/4) - 1 = +1%
    raw = decide(())
    assert raw.intent == Intent.NO_TRADE and "r_early=-0.7475" in raw.rationale


def test_early_closes_abstain_without_skipping_back() -> None:
    early_day = run([(D1, "13:00", {}), (D2, "16:00", UP)])
    assert early_day[0].reasons == ("early_close",)
    assert early_day[0].generated_at == local_ns(D1, "13:00") + SECOND
    assert early_day[1].intent == Intent.NO_TRADE
    assert early_day[1].reasons == ("previous_early_close",)
    assert run([(D1, "16:00", {}), (D2, "13:00", UP)])[-1].reasons == ("early_close",)


def test_missing_or_empty_inputs_fail_closed_with_reasons() -> None:
    calendar = Calendar((SessionSpec(D1), SessionSpec(D2)))

    def with_day2(candles: list[Candle]) -> Proposal:
        rule = ItsmRule(ItsmParams(), "SYNTH.XNAS", calendar)
        out = [x for c in [*day_candles(D1), *candles] if (x := rule.on_candle(c))]
        return out[-1]

    day2 = day_candles(D2, at=UP)
    ten = local_ns(D2, "10:00")
    p = with_day2([c for c in day2 if c.end != ten])
    assert p.intent == Intent.NO_TRADE
    assert set(p.reasons) == {"unavailable:early", "unknown_gap_before_decision"}
    zero = [replace(c, volume=0) if c.end == local_ns(D2, "15:00") else c for c in day2]
    assert with_day2(zero).reasons == ("unavailable:preclose_start",)
    first = ItsmRule(ItsmParams(), "SYNTH.XNAS", Calendar((SessionSpec(D1),)))
    out = [x for c in day_candles(D1) if (x := first.on_candle(c))]
    assert out[0].intent == Intent.NO_TRADE and "previous_session_unknown" in out[0].reasons


def test_one_proposal_per_session_and_replay_is_deterministic() -> None:
    sessions = [(D1, "16:00", {}), (D2, "16:00", UP), ("2022-03-09", "16:00", DOWN)]
    first = run(sessions)
    assert len(first) == 3 and first == run(sessions)


def test_decision_ignores_everything_after_the_decision_candle() -> None:
    calendar = Calendar((SessionSpec(D1), SessionSpec(D2)))
    stream = [*day_candles(D1), *day_candles(D2, at=UP)]
    cut = next(i for i, c in enumerate(stream) if c.end == local_ns(D2, "15:30")) + 1
    wild = [
        replace(c, open=c.open + 50, high=c.high + 60, low=c.low + 40, close=c.close + 55)
        for c in stream[cut:]
    ]

    def proposals(candles: list[Candle]) -> list[Proposal]:
        rule = ItsmRule(ItsmParams(), "SYNTH.XNAS", calendar)
        return [x for c in candles if (x := rule.on_candle(c))]

    assert proposals(stream[:cut]) == proposals(stream) == proposals(stream[:cut] + wild)


def test_parameter_validation() -> None:
    for bad in (
        {"early_end": "9:60"},
        {"early_end": "15:10", "preclose_start": "15:00"},
        {"decision": "16:00"},
        {"entry_valid_seconds": 0},
        {"splits": (("2022-03-08", Decimal(0)),)},
    ):
        with pytest.raises(DataError):
            ItsmParams(**bad)
