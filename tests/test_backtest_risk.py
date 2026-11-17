"""Sizing, deterministic risk limits and exit policy."""

from decimal import Decimal

import pytest

from drift.backtest.risk import ExitPolicy, Protection, RiskLimits, Sizing
from drift.data.model import SECOND, DataError

D = Decimal


def limits(**kw: object) -> RiskLimits:
    base = {
        "max_quantity": D(100),
        "max_notional": D(20000),
        "max_leverage": D(1),
        "max_entries_per_session": 2,
        "max_session_loss": D(500),
        "max_data_age_seconds": 120,
    }
    return RiskLimits(**(base | kw))  # type: ignore[arg-type]


def check(**kw: object) -> tuple[str, ...]:
    args = {
        "quantity": D(100),
        "price": D(100),
        "multiplier": D(1),
        "balance": D(100000),
        "data_age_ns": 60 * SECOND,
        "entries_today": 0,
        "loss_today": D(0),
    }
    return limits().check_entry(**(args | kw))  # type: ignore[arg-type]


def test_sizing_rounds_down_to_whole_lots() -> None:
    assert Sizing("fixed_quantity", D(25)).quantity(D(100), D(1), D(1)) == 25
    notional = Sizing("target_notional", D(10000))
    assert notional.quantity(D(100), D(1), D(1)) == 100
    assert notional.quantity(D(333), D(1), D(1)) == 30  # 30.03 shares floors to 30
    assert notional.quantity(D(133), D(1), D(10)) == 70  # 75.18 floors to 7 lots of 10
    assert Sizing("target_notional", D(50000)).quantity(D(5000), D(5), D(1)) == 2  # multiplier
    assert Sizing("target_notional", D(50)).quantity(D(100), D(1), D(1)) == 0  # cannot afford one


def test_sizing_validation() -> None:
    for mode, amount in (("kelly", D(1)), ("fixed_quantity", D(0)), ("target_notional", D(-5))):
        with pytest.raises(DataError):
            Sizing(mode, amount)


def test_limits_have_no_defaults_and_must_be_positive() -> None:
    with pytest.raises(TypeError):
        RiskLimits()  # type: ignore[call-arg]
    for field in (
        "max_quantity",
        "max_notional",
        "max_leverage",
        "max_entries_per_session",
        "max_session_loss",
        "max_data_age_seconds",
    ):
        with pytest.raises(DataError):
            limits(**{field: 0})


def test_entry_checks_report_every_violation_with_stable_codes() -> None:
    assert check() == ()
    assert check(quantity=D(0)) == ("quantity_below_lot",)
    assert check(quantity=D(101)) == ("quantity_exceeds_limit",)
    assert check(price=D(300)) == ("notional_exceeds_limit",)
    assert check(balance=D(5000)) == ("leverage_exceeds_limit",)
    assert check(balance=D(0)) == ("leverage_exceeds_limit",)
    assert check(data_age_ns=121 * SECOND) == ("stale_data",)
    assert check(data_age_ns=120 * SECOND) == ()  # the limit itself is allowed
    assert check(entries_today=2) == ("session_entry_limit_reached",)
    assert check(loss_today=D(500)) == ("session_loss_limit_reached",)
    assert set(check(quantity=D(500), entries_today=9)) == {
        "quantity_exceeds_limit",
        "notional_exceeds_limit",
        "session_entry_limit_reached",
    }  # 50,000 notional is within 1x leverage of a 100,000 balance


def test_notional_uses_the_multiplier() -> None:
    # 2 contracts x 5000 x 5 = 50,000 notional against a 20,000 cap
    codes = check(price=D(5000), multiplier=D(5), quantity=D(2), balance=D(100000))
    assert codes == ("notional_exceeds_limit",)
    assert check(price=D(5000), multiplier=D(1), quantity=D(2)) == ()  # 10,000 without it


def test_protection_distance_is_tick_rounded_and_at_least_one_tick() -> None:
    tick = D("0.01")
    assert Protection("ticks", D(20)).distance(D(100), tick) == D("0.20")
    assert Protection("percent", D("0.5")).distance(D(100), tick) == D("0.50")
    assert Protection("percent", D("0.123")).distance(D(100), tick) == D("0.12")
    assert Protection("percent", D("0.0001")).distance(D(100), tick) == D("0.01")
    assert Protection("ticks", D(3)).distance(D(5000), D("0.25")) == D("0.75")
    for kind, value in (("atr", D(1)), ("ticks", D(0))):
        with pytest.raises(DataError):
            Protection(kind, value)


def test_exit_policy_levels_for_both_sides() -> None:
    policy = ExitPolicy(
        horizon_seconds=600, stop=Protection("ticks", D(20)), target=Protection("percent", D(1))
    )
    tick = D("0.01")
    assert policy.levels(1, D("100.01"), tick) == (D("99.81"), D("101.01"))
    assert policy.levels(-1, D("100.01"), tick) == (D("100.21"), D("99.01"))
    assert ExitPolicy(horizon_seconds=60).levels(1, D(100), tick) == (None, None)
    with pytest.raises(DataError, match="positive"):
        ExitPolicy(horizon_seconds=60, stop=Protection("ticks", D(20))).levels(1, D("0.10"), tick)


def test_exit_policy_requires_a_time_exit() -> None:
    with pytest.raises(DataError):
        ExitPolicy(horizon_seconds=None, flatten_lead_seconds=None)
    with pytest.raises(DataError):
        ExitPolicy(horizon_seconds=0)
    assert ExitPolicy().flatten_lead_seconds == 120 and ExitPolicy().stop is None
