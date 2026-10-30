"""Configuration parsing, synthetic data determinism and report metrics."""

import json
from decimal import Decimal

import pytest
from helpers import make_config, merge

from quantlab.backtest.config import STRATEGIES, BacktestConfig, default_config
from quantlab.backtest.data import InstrumentSpec, SyntheticSpec, generate
from quantlab.backtest.report import Trade, metrics
from quantlab.data.model import SECOND, DataError, canonical, digest


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_default_configurations_parse_and_resolve_every_default(strategy: str) -> None:
    config = BacktestConfig.parse(default_config(strategy))
    payload = config.payload()
    assert payload["strategy"]["name"] == strategy
    assert payload["strategy"]["exit"]["flatten_lead_seconds"] == 120
    json.dumps(payload)  # JSON-serializable, no Decimals leaked
    if strategy == "candlestick":
        assert payload["strategy"]["params"]["detector"]["star_penetration"] == "0.50"
        assert payload["strategy"]["exit"]["horizon_seconds"] == 1800  # derived default
        assert payload["strategy"]["params"]["filters"]["trend"] is None  # filters off


@pytest.mark.parametrize(
    "patch",
    [
        {"capital": 100000.5},  # floats are never accepted for money
        {"capital": "100000.555"},  # the engine books whole cents, so the ledger must too
        {"name": "x\n## forged section"},
        {"strategy": {"name": []}},
        {"strategy": {"name": "itsm", "params": {"splits": [["2021-7-20", "4"]]}}},
        {"synthetic": False},
        {"version": 2},
        {"risk": {"max_notional": "0"}},
        {"sizing": {"mode": "kelly"}},
        {"sizing": {"amount": "2.5"}},  # fixed quantity must be a whole number of lots
        {"instrument": {"kind": "equity", "multiplier": 5}},
        {"instrument": {"currency": "EUR"}},
        {"execution": {"order_latency_seconds": -1}},
        {"execution": {"order_latency_seconds": 60}},  # flatten lead 120 <= 60 + 60
        {"strategy": {"name": "martingale"}},
        {"strategy": {"name": "itsm", "params": {"mystery": 1}}},
        {
            "strategy": {
                "name": "itsm",
                "exit": {"horizon_seconds": None, "flatten_lead_seconds": None},
            }
        },
        {"strategy": {"name": "itsm", "exit": {"flatten_lead_seconds": 30}}},
        {"strategy": {"name": "itsm", "params": {"entry_valid_seconds": 30}}},
    ],
)
def test_invalid_configurations_are_rejected(patch: dict) -> None:
    raw = merge(default_config("itsm"), patch)
    if "strategy" in patch:
        raw["strategy"] = patch["strategy"]
    with pytest.raises((DataError, ValueError)):
        BacktestConfig.parse(raw)


def test_costs_sizing_and_risk_cannot_be_omitted() -> None:
    for section in ("execution", "sizing", "risk", "instrument", "data"):
        raw = default_config("itsm")
        del raw[section]
        with pytest.raises(DataError):
            BacktestConfig.parse(raw)
    raw = default_config("itsm")
    del raw["risk"]["max_session_loss"]
    with pytest.raises(DataError):
        BacktestConfig.parse(raw)


def test_candlestick_params_are_parsed_from_json_exactly() -> None:
    raw = default_config("candlestick")
    raw["strategy"]["params"] |= {
        "patterns": ["hammer", "doji"],
        "timeframes": [5, 15],
        "detector": {"inclusive": False, "star_penetration": "0.4"},
        "filters": {"volume": {"lookback": 5, "min_multiple": "1.5"}, "trend": {"lookback": 4}},
    }
    raw["strategy"]["exit"] = {
        "horizon_seconds": 900,
        "stop": {"kind": "ticks", "value": "30"},
        "target": {"kind": "percent", "value": "0.5"},
    }
    config = BacktestConfig.parse(raw)
    params = config.strategy.params
    assert params.timeframes == (5, 15) and params.detector.inclusive is False  # type: ignore[union-attr]
    assert params.filters.volume.min_multiple == Decimal("1.5")  # type: ignore[union-attr]
    assert config.strategy.exit.stop.value == 30  # type: ignore[union-attr]
    raw["strategy"]["params"]["patterns"] = ["moon"]
    with pytest.raises(DataError):
        BacktestConfig.parse(raw)


def test_config_hash_ignores_key_order_but_not_values() -> None:
    a = make_config("itsm").payload()
    raw = default_config("itsm")
    reordered = dict(reversed(list(raw.items())))
    assert digest(canonical(BacktestConfig.parse(reordered).payload())) == digest(canonical(a))
    assert digest(canonical(make_config("itsm", capital="99999").payload())) != digest(canonical(a))


def spec(**kw: object) -> SyntheticSpec:
    base = default_config("itsm")["data"] | {
        "open_price": Decimal("100.00"),
        "early_close_days": (),
        "holidays": (),
    }
    return SyntheticSpec(**(base | kw))  # type: ignore[arg-type]


EQUITY = InstrumentSpec("SYNTH", "XNAS", "equity", "USD", Decimal("0.01"), 1, 1)


def test_generation_is_deterministic_and_seed_sensitive() -> None:
    a = generate(spec(sessions=3), EQUITY)
    assert (
        a == generate(spec(sessions=3), EQUITY)
        and a.sha256 == generate(spec(sessions=3), EQUITY).sha256
    )
    assert generate(spec(sessions=3, seed=8), EQUITY).sha256 != a.sha256
    assert len(a.candles) == 3 * 390


def test_generated_candles_respect_ticks_availability_and_calendar() -> None:
    data = generate(
        spec(
            sessions=4,
            start_day="2022-03-10",
            early_close_days=("2022-03-14",),
            holidays=("2022-03-11",),
        ),
        EQUITY,
    )
    assert [s.day for s in data.calendar.sessions] == [
        "2022-03-10",
        "2022-03-14",  # weekend and the holiday are skipped
        "2022-03-15",
        "2022-03-16",
    ]
    assert data.calendar.get("2022-03-14").cash_close == "13:00"  # type: ignore[union-attr]
    early = [c for c in data.candles if c.day == "2022-03-14"]
    assert len(early) == 210  # 09:30-13:00
    for c in data.candles:
        assert c.available == c.end + 1 * SECOND and c.end - c.start == 60 * SECOND
        assert all(p % Decimal("0.01") == 0 for p in (c.open, c.high, c.low, c.close))
        assert c.volume >= 1000
    gaps = {
        abs(b.open - a.close)
        for a, b in zip(data.candles, data.candles[1:], strict=False)
        if a.day == b.day
    }
    assert gaps == {Decimal(0)}  # within a session each open is the previous close


def test_spec_validation() -> None:
    for bad in ({"sessions": 0}, {"delay_seconds": 60}, {"volume": 1}, {"step_ticks": -1}):
        with pytest.raises(DataError):
            spec(**bad)
    with pytest.raises(DataError):
        InstrumentSpec("S", "V", "equity", "USD", Decimal(0), 1, 1)


def trade(n: int, net: str, seconds: int = 600, side: str = "LONG") -> Trade:
    gross = Decimal(net) + 2
    return Trade(
        n,
        side,
        Decimal(10),
        0,
        seconds * SECOND,
        Decimal(100),
        Decimal(101),
        gross,
        Decimal(2),
        Decimal(net),
        "horizon",
        "s",
        f"p{n}",
    )


def test_metrics_match_hand_calculation() -> None:
    trades = [trade(1, "10"), trade(2, "-4"), trade(3, "-6", side="SHORT"), trade(4, "20")]
    m = metrics(trades, Decimal(1000), 40000 * SECOND)
    assert (m["trades"], m["long_trades"], m["short_trades"]) == (4, 3, 1)
    assert (m["net_pnl"], m["gross_pnl"], m["commissions"]) == ("20", "28", "8")
    assert m["net_return"] == "0.02" and m["ending_equity"] == "1020"
    assert m["win_rate"] == "0.5" and m["average_win"] == "15" and m["average_loss"] == "-5"
    assert m["profit_factor"] == "3" and m["expectancy_per_trade"] == "5"
    assert m["max_drawdown"] == "10"  # equity 1010 -> 1006 -> 1000, from the 1010 peak
    assert Decimal(m["max_drawdown_pct"]) == Decimal(10) / 1010
    assert m["average_holding_seconds"] == "600" and m["exposure_fraction"] == "0.06"
    assert m["exit_reasons"] == {"horizon": 4}


def test_metrics_without_trades_or_losses_do_not_divide_by_zero() -> None:
    empty = metrics([], Decimal(1000), 1000 * SECOND)
    assert empty["trades"] == 0 and empty["win_rate"] is None and empty["profit_factor"] is None
    assert empty["net_pnl"] == "0" and empty["max_drawdown"] == "0"
    winners = metrics([trade(1, "5")], Decimal(1000), 1000 * SECOND)
    assert winners["profit_factor"] is None and winners["average_loss"] is None


def parsed(strategy: str, params: dict) -> BacktestConfig:
    raw = default_config(strategy)
    raw["strategy"]["params"] = params
    return BacktestConfig.parse(raw)


def test_statistical_strategy_parameters_parse_exactly_with_their_exit_defaults() -> None:
    orb = parsed(
        "orb",
        {
            "range_minutes": 30,
            "entry_cutoff": "11:30",
            "rvol_min": "1.2",
            "rvol_lookback": 10,
            "vwap_alignment": True,
            "breakout_volume_multiple": "1.5",
            "prior_tr_below_atr": 20,
        },
    )
    p = orb.strategy.params
    assert (p.range_minutes, p.rvol_min, p.prior_tr_below_atr) == (30, Decimal("1.2"), 20)  # type: ignore[union-attr]
    assert p.breakout_volume_multiple == Decimal("1.5") and p.vwap_alignment is True  # type: ignore[union-attr]
    assert orb.strategy.exit.horizon_seconds == 1800 and not orb.strategy.exit.exit_on_opposite

    vwap = parsed(
        "vwap_reversion", {"sigma_multiple": "2.5", "min_bars": 45, "window_start": "11:00"}
    )
    assert vwap.strategy.params.sigma_multiple == Decimal("2.5")  # type: ignore[union-attr]
    assert vwap.strategy.params.min_bars == 45 and vwap.strategy.exit.horizon_seconds == 1200  # type: ignore[union-attr]

    boll = parsed("bollinger_reversion", {"timeframe": 15, "period": 10})
    assert (boll.strategy.params.timeframe, boll.strategy.params.period) == (15, 10)  # type: ignore[union-attr]

    rev = parsed("reversal", {"timeframe": 5, "min_abs_return_bps": "15", "allow_short": False})
    assert rev.strategy.params.min_abs_return_bps == Decimal(15)  # type: ignore[union-attr]
    assert rev.strategy.params.allow_short is False and rev.strategy.exit.horizon_seconds == 900  # type: ignore[union-attr]

    trend = parsed("trend", {"timeframe": 15, "fast": 3, "slow": 9})
    assert trend.strategy.exit.horizon_seconds is None and trend.strategy.exit.exit_on_opposite
    assert trend.payload()["strategy"]["params"]["slow"] == 9


@pytest.mark.parametrize(
    ("strategy", "params"),
    [
        ("orb", {"range_minutes": 10}),
        ("orb", {"rvol_min": 1.2}),  # floats are never accepted
        ("orb", {"mystery": 1}),
        ("vwap_reversion", {"window_start": "14:00", "window_end": "11:30"}),
        ("bollinger_reversion", {"period": 1}),
        ("bollinger_reversion", {"min_bars": 30}),  # a VWAP-only key
        ("reversal", {"timeframe": 7}),
        ("trend", {"fast": 9, "slow": 3}),
        ("trend", {"horizon_seconds": 60}),
    ],
)
def test_invalid_statistical_strategy_parameters_are_rejected(strategy: str, params: dict) -> None:
    with pytest.raises(DataError):
        parsed(strategy, params)


def test_every_strategy_has_a_resolved_payload_with_no_floats() -> None:
    for strategy in STRATEGIES:
        payload = BacktestConfig.parse(default_config(strategy)).payload()
        assert payload["strategy"]["name"] == strategy
        assert "float" not in json.dumps(payload) and json.loads(json.dumps(payload)) == payload
