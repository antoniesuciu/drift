"""Full execution path through NautilusTrader with hand-computed expectations (synthetic only)."""

import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from helpers import make_config, merge, scripted_market

from drift.backtest.config import STRATEGIES, BacktestConfig
from drift.backtest.data import MarketData, generate
from drift.backtest.engine import run_backtest, run_on
from drift.backtest.report import BacktestResult
from drift.data.model import SECOND, DataError, local_ns

D1, D2, D3 = "2022-03-07", "2022-03-08", "2022-03-09"
UP = {"10:00": "101.00", "15:00": "100.50", "15:30": "101.00"}
DOWN = {"10:00": "99.00", "15:00": "99.50", "15:30": "99.00"}
COSTS = {"execution": {"sell_pct_notional": "0.001"}, "sizing": {"amount": "10"}}


def itsm(sessions: list[tuple[str, str, dict[str, Any]]], **patch: Any) -> BacktestResult:
    config = make_config("itsm", **merge(COSTS, patch))
    return run_on(config, scripted_market(config.instrument, sessions))


def test_itsm_long_matches_a_hand_calculation_end_to_end() -> None:
    r = itsm([(D1, "16:00", {}), (D2, "16:00", UP)])
    (t,) = r.trades
    assert (t.side, t.quantity, t.exit_reason) == ("LONG", 10, "session_flatten")
    # decision 15:30:01 -> first bar starting strictly after: 15:31; exit decided 15:58 -> 15:59
    assert t.entry_ts == local_ns(D2, "15:31") and t.exit_ts == local_ns(D2, "15:59")
    assert t.entry_price == Decimal("100.01")  # open 100.00 + 1 tick half-spread (ask)
    assert t.exit_price == Decimal("99.99")  # open 100.00 - 1 tick (bid)
    assert t.gross_pnl == Decimal("-0.20")
    # entry 0.35 minimum; exit 0.35 + 0.1% of 999.90 = 0.9999 -> engine rounds 1.3499 to 1.35
    assert t.commission == Decimal("1.70") and t.net_pnl == Decimal("-1.90")
    assert r.metrics["ending_equity"] == "99998.10"
    assert r.engine["orders"] == 2 and r.engine["positions"] == 1
    assert r.reconciliation["engine_balance"] == "99998.1" and r.reconciliation["ok"]
    assert [p["status"] for p in r.proposals] == ["no_trade", "filled"]
    assert r.open_at_end is None and r.rejections == ()


def test_itsm_short_sells_at_the_bid_and_buys_back_at_the_ask() -> None:
    r = itsm([(D1, "16:00", {}), (D2, "16:00", DOWN)])
    (t,) = r.trades
    assert t.side == "SHORT" and t.entry_price == Decimal("99.99")
    assert t.exit_price == Decimal("100.01") and t.gross_pnl == Decimal("-0.20")
    # entry sells: 0.35 + 0.1% of 999.90 -> 1.35; exit buys: 0.35 with no sell-side fee
    assert t.commission == Decimal("1.70") and r.reconciliation["ok"]


def test_futures_use_the_multiplier_tick_and_per_contract_fees() -> None:
    patch = {
        "instrument": {
            "symbol": "MESX",
            "venue": "XCME",
            "kind": "future",
            "tick": "0.25",
            "multiplier": 5,
        },
        "sizing": {"amount": "2"},
        "risk": {"max_notional": "100000"},
        "execution": {"sell_pct_notional": "0"},
    }
    config = make_config("itsm", **patch)
    up = {"10:00": "5010.00", "15:00": "5005.00", "15:30": "5010.00"}
    r = run_on(
        config,
        scripted_market(config.instrument, [(D1, "16:00", {}), (D2, "16:00", up)], "5000.00"),
    )
    (t,) = r.trades
    assert (t.entry_price, t.exit_price) == (Decimal("5000.25"), Decimal("4999.75"))
    assert t.gross_pnl == Decimal("-5.00")  # (4999.75 - 5000.25) x 2 contracts x 5
    assert t.commission == Decimal("0.70") and t.net_pnl == Decimal("-5.70")
    assert r.reconciliation["engine_balance"] == "99994.3" and r.reconciliation["ok"]


@pytest.mark.parametrize(("latency", "entry"), [(0, "15:31"), (58, "15:31"), (59, "15:32")])
def test_order_latency_pushes_the_fill_to_a_later_bar(latency: int, entry: str) -> None:
    r = itsm([(D1, "16:00", {}), (D2, "16:00", UP)], execution={"order_latency_seconds": latency})
    assert r.trades[0].entry_ts == local_ns(D2, entry)  # strictly after decision + latency


def test_spread_and_slippage_each_count_once_and_costs_scale() -> None:
    free = itsm([(D1, "16:00", {}), (D2, "16:00", UP)], execution={"half_spread_ticks": 0})
    assert (free.trades[0].entry_price, free.trades[0].exit_price) == (Decimal(100), Decimal(100))
    both = itsm(
        [(D1, "16:00", {}), (D2, "16:00", UP)],
        execution={"half_spread_ticks": 2, "slippage_ticks": 3},
    )
    assert both.trades[0].entry_price == Decimal("100.05") and both.trades[0].exit_price == Decimal(
        "99.95"
    )
    assert both.trades[0].gross_pnl == Decimal("-1.00")


def test_commission_minimum_cap_and_per_unit_scale() -> None:
    big = itsm(
        [(D1, "16:00", {}), (D2, "16:00", UP)],
        sizing={"amount": "1000"},
        risk={"max_quantity": "5000", "max_notional": "200000"},
        execution={"sell_pct_notional": "0"},
        capital="200000",
    )
    # 1000 x 0.0035 = 3.50 per order, above the 0.35 minimum and below the 1% cap
    assert big.trades[0].commission == Decimal("7.00")
    capped = itsm(
        [(D1, "16:00", {}), (D2, "16:00", UP)],
        execution={"per_unit": "0.5", "sell_pct_notional": "0"},
    )
    # 10 x 0.5 = 5.00 per order is capped at 1% of notional (about 10.00): not binding; 5.00 x 2
    assert capped.trades[0].commission == Decimal("10.00")
    tight = itsm(
        [(D1, "16:00", {}), (D2, "16:00", UP)],
        execution={"per_unit": "0.5", "max_pct_notional": "0.002", "sell_pct_notional": "0"},
    )
    assert tight.trades[0].commission == Decimal("4.00")  # capped at 0.2% x ~1000 = 2.00 per order


def test_risk_rejection_blocks_the_order_and_is_reported() -> None:
    r = itsm([(D1, "16:00", {}), (D2, "16:00", UP)], risk={"max_notional": "500"})
    assert r.trades == () and r.engine["orders"] == 0
    (rejection,) = r.rejections
    assert rejection["source"] == "risk" and rejection["reasons"] == ["notional_exceeds_limit"]
    assert r.proposals[-1]["status"] == "rejected:notional_exceeds_limit"
    assert r.metrics["trades"] == 0 and r.reconciliation["ok"]


def test_overnight_position_is_forced_flat_and_flagged() -> None:
    patch = {
        "strategy": {
            "name": "itsm",
            "exit": {"horizon_seconds": 36000, "flatten_lead_seconds": None},
        }
    }
    r = itsm([(D1, "16:00", {}), (D2, "16:00", UP), (D3, "16:00", {})], **patch)
    (t,) = r.trades
    assert t.exit_reason == "missed_cutoff_forced" and t.flags == ("missed_cutoff",)
    assert t.exit_ts == local_ns(D3, "09:30") and r.reconciliation["ok"]


def test_position_left_open_at_the_end_is_reported_not_invented_away() -> None:
    patch = {
        "strategy": {
            "name": "itsm",
            "exit": {"horizon_seconds": 36000, "flatten_lead_seconds": None},
        }
    }
    r = itsm([(D1, "16:00", {}), (D2, "16:00", UP)], **patch)
    assert r.trades == () and r.open_at_end is not None
    assert r.open_at_end["side"] == "LONG" and r.open_at_end["entry_price"] == "100.01"
    assert r.reconciliation["ok"] and r.reconciliation["ledger_balance"] == "99999.65"


CROSS = {"10:00": ("100.00", "101.00", "100.00", "101.00")}  # trend LONG, filled 10:01


def protected_trade(at: dict[str, Any], **exit_policy: Any) -> BacktestResult:
    # Long-only trend with the opposite-signal exit off, so only the exit policy can close it.
    exit_ = {"flatten_lead_seconds": 120, "exit_on_opposite": False} | exit_policy
    patch = {
        "sizing": {"amount": "10"},
        "strategy": {
            "name": "trend",
            "params": {"timeframe": 5, "fast": 2, "slow": 4, "allow_short": False},
            "exit": exit_,
        },
    }
    config = make_config("trend", **patch)
    return run_on(config, scripted_market(config.instrument, [(D2, "16:00", CROSS | at)]))


STOP = {"kind": "ticks", "value": "20"}


def test_stop_loss_exits_at_the_next_open_paying_for_the_gap() -> None:
    at = {"10:05": ("100.00", "100.00", "99.80", "99.85"), "10:07": "99.50"}
    r = protected_trade(at, stop=STOP)
    t = r.trades[0]  # the later re-cross may enter again
    assert t.entry_ts == local_ns(D2, "10:01") and t.entry_price == Decimal("100.01")
    # stop level is 99.81; the bar completes 10:05, the exit fills at the 10:06 open (99.50 - tick)
    assert t.exit_reason == "stop_loss" and t.exit_ts == local_ns(D2, "10:06")
    assert t.exit_price == Decimal("99.49") and t.gross_pnl == Decimal("-5.20")
    assert t.flags == () and r.reconciliation["ok"]


def test_take_profit_exit() -> None:
    at = {"10:05": ("100.00", "100.25", "100.00", "100.20"), "10:07": "100.30"}
    t = protected_trade(at, stop=STOP, target={"kind": "ticks", "value": "20"}).trades[0]
    assert t.exit_reason == "take_profit" and t.exit_price == Decimal("100.29")
    assert t.gross_pnl == Decimal("2.80")


def test_a_bar_touching_both_levels_is_a_stop() -> None:
    at = {"10:05": ("100.00", "100.30", "99.80", "100.00"), "10:07": "99.90"}
    t = protected_trade(at, stop=STOP, target={"kind": "ticks", "value": "20"}).trades[0]
    assert t.exit_reason == "stop_loss" and t.flags == ("stop_and_target_same_bar",)
    assert t.exit_price == Decimal("99.89")


def test_horizon_and_flatten_exits_without_protection() -> None:
    t = protected_trade({}, horizon_seconds=600).trades[0]
    assert t.exit_reason == "horizon" and t.exit_ts == local_ns(
        D2, "10:12"
    )  # 10:01 + 10m, strictly after
    t = protected_trade({}, horizon_seconds=7 * 3600).trades[0]
    assert t.exit_reason == "session_flatten" and t.exit_ts == local_ns(D2, "15:59")


def small(strategy: str, **patch: Any) -> BacktestConfig:
    data = {"data": {"sessions": 6}}
    return make_config(strategy, **merge(data, patch))


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_no_fill_precedes_decision_time_or_the_bar_open(strategy: str) -> None:
    config = small(strategy, execution={"order_latency_seconds": 30})
    data = generate(config.data, config.instrument)
    opens = {c.start: c for c in data.candles}
    result = run_on(config, data)
    assert result.trades  # the property below must not be vacuous
    by_id = {p["proposal_id"]: p for p in result.proposals}
    offset = Decimal("0.01") * config.costs.half_spread_ticks
    for t in result.trades:
        decided = by_id[t.proposal_id]["generated_at"]
        assert t.entry_ts > decided + 30 * SECOND  # never at or before availability + latency
        entry, exit_ = opens[t.entry_ts], opens[t.exit_ts]
        assert t.entry_price == entry.open + (offset if t.side == "LONG" else -offset)
        assert t.exit_price == exit_.open + (-offset if t.side == "LONG" else offset)
        assert t.exit_ts > t.entry_ts
    assert result.reconciliation["ok"]


def outcome(result: BacktestResult, cut: int) -> tuple[Any, Any]:
    proposals = [
        (p["proposal_id"], p["intent"], tuple(p["reasons"]), p["rationale"])
        for p in result.proposals
        if p["generated_at"] < cut
    ]
    trades = [t.row() for t in result.trades if t.exit_ts < cut]
    return proposals, trades


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_changing_the_future_cannot_change_earlier_decisions_or_trades(strategy: str) -> None:
    config = small(strategy)
    data = generate(config.data, config.instrument)
    cut_index = 3 * 390
    cut = data.candles[cut_index].start
    shifted = tuple(
        c
        if i < cut_index
        else replace(c, open=c.open + 7, high=c.high + 9, low=c.low + 5, close=c.close + 8)
        for i, c in enumerate(data.candles)
    )
    altered = MarketData.build(data.instrument, data.calendar, shifted)
    assert altered.sha256 != data.sha256
    full, perturbed = run_on(config, data), run_on(config, altered)
    before = outcome(full, cut)
    assert before == outcome(perturbed, cut) and before[0]
    truncated = MarketData.build(data.instrument, data.calendar, data.candles[:cut_index])
    assert outcome(run_on(config, truncated), cut)[0] == before[0]  # the future may be absent


def test_same_inputs_reproduce_identical_results_and_files(tmp_path: Path) -> None:
    config = small("trend")
    first, second = run_backtest(config), run_backtest(config)
    assert first.results_sha256 == second.results_sha256
    assert first.to_dict() == second.to_dict() and first.trades_csv() == second.trades_csv()
    first.write(tmp_path / "a")
    second.write(tmp_path / "b")
    for name in ("report.json", "report.md", "trades.csv"):
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes()
    reseeded = run_backtest(small("trend", data={"seed": 99}))
    assert reseeded.data_sha256 != first.data_sha256
    assert reseeded.results_sha256 != first.results_sha256
    report = json.loads((tmp_path / "a" / "report.json").read_text())
    assert report["synthetic"] is True and report["results_sha256"] == first.results_sha256


def test_market_data_must_match_the_configured_instrument() -> None:
    config = make_config("itsm")
    other = replace(config.instrument, symbol="OTHER")
    with pytest.raises(DataError, match="instrument"):
        run_on(config, scripted_market(other, [(D1, "16:00", {})]))


def test_market_data_rejects_availability_running_backwards() -> None:
    config = make_config("itsm")
    data = scripted_market(config.instrument, [(D1, "16:00", {})])
    first, second = data.candles[:2]
    late = replace(first, available=second.available + SECOND)
    with pytest.raises(DataError, match="ordered"):
        MarketData.build(config.instrument, data.calendar, (late, second))


def test_markdown_report_lists_trades_metrics_and_limits() -> None:
    r = itsm([(D1, "16:00", {}), (D2, "16:00", UP)])
    text = r.markdown()
    for needle in (
        "Synthetic data",
        "net_pnl",
        "-1.90",
        "Reconciliation",
        "session_flatten",
        "| 1 | LONG",
    ):
        assert needle in text
    assert "profitability" in text and r.results_sha256[:16] in text
    csv = r.trades_csv().splitlines()
    assert csv[0].startswith("number,side") and len(csv) == 2


def flat_day(at: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    return [(D2, "16:00", at)]


def single_trade(strategy: str, params: dict[str, Any], at: dict[str, Any]) -> BacktestResult:
    patch = COSTS | {"strategy": {"name": strategy, "params": params}}
    config = make_config(strategy, **patch)
    return run_on(config, scripted_market(config.instrument, flat_day(at)))


def test_orb_breakout_trade_matches_a_hand_calculation() -> None:
    at = {
        "09:40": ("100.00", "101.00", "99.00", "100.00"),  # opening range 99.00-101.00
        "09:50": ("100.00", "101.60", "100.00", "101.50"),  # first close beyond it: LONG
    }
    r = single_trade("orb", {}, at)
    (t,) = r.trades
    # decided 09:50:01 -> fills at the 09:51 open; horizon 30 min from the fill -> 10:22 open
    assert (t.side, t.exit_reason) == ("LONG", "horizon")
    assert t.entry_ts == local_ns(D2, "09:51") and t.exit_ts == local_ns(D2, "10:22")
    assert (t.entry_price, t.exit_price) == (Decimal("100.01"), Decimal("99.99"))
    assert t.gross_pnl == Decimal("-0.20") and t.net_pnl == Decimal("-1.90")
    assert [p["status"] for p in r.proposals] == ["filled"] and r.reconciliation["ok"]


def test_reversal_trade_fades_the_first_bucket_and_exits_on_its_horizon() -> None:
    r = single_trade("reversal", {}, {"09:45": ("100.00", "100.00", "99.00", "99.00")})
    (t,) = r.trades  # -1% over 09:30-09:45 -> LONG; later buckets are flat (no signal)
    assert (t.side, t.exit_reason) == ("LONG", "horizon")
    assert t.entry_ts == local_ns(D2, "09:46") and t.exit_ts == local_ns(D2, "10:02")
    assert t.gross_pnl == Decimal("-0.20") and t.net_pnl == Decimal("-1.90")


def test_trend_crossover_enters_and_the_opposite_cross_exits() -> None:
    at = {"10:00": ("100.00", "101.00", "100.00", "101.00")}  # bucket 6 closes 101, then flat
    r = single_trade("trend", {"timeframe": 5, "fast": 2, "slow": 4}, at)
    (t,) = r.trades
    assert (t.side, t.exit_reason) == ("LONG", "opposite_signal")
    assert t.entry_ts == local_ns(D2, "10:01") and t.exit_ts == local_ns(D2, "10:11")
    assert t.net_pnl == Decimal("-1.90") and r.reconciliation["ok"]
    assert [p["status"] for p in r.proposals] == ["filled", "queued_exit"]


def test_long_only_trend_still_exits_on_the_disabled_cross() -> None:
    at = {"10:00": ("100.00", "101.00", "100.00", "101.00")}
    params = {"timeframe": 5, "fast": 2, "slow": 4, "allow_short": False}
    r = single_trade("trend", params, at)
    (t,) = r.trades
    assert (t.side, t.exit_reason) == ("LONG", "opposite_signal")
    assert t.exit_ts == local_ns(D2, "10:11")
    assert [p["intent"] for p in r.proposals] == ["LONG", "FLAT"]


def test_flat_request_respects_a_disabled_opposite_exit() -> None:
    patch = COSTS | {
        "strategy": {
            "name": "trend",
            "params": {"timeframe": 5, "fast": 2, "slow": 4, "allow_short": False},
            "exit": {"exit_on_opposite": False},
        }
    }
    config = make_config("trend", **patch)
    at = {"10:00": ("100.00", "101.00", "100.00", "101.00")}
    r = run_on(config, scripted_market(config.instrument, flat_day(at)))
    (t,) = r.trades
    assert t.exit_reason == "session_flatten"
    assert [p["status"] for p in r.proposals] == ["filled", "ignored:position_open"]


def test_engine_rejection_is_visible_on_the_proposal(monkeypatch: pytest.MonkeyPatch) -> None:
    from drift.backtest import engine

    def deny(self: Any, order: Any) -> None:
        self._engine_reject(SimpleNamespace(ts_event=1, reason="denied"))

    monkeypatch.setattr(engine.RuleStrategy, "submit_order", deny)
    r = itsm([(D1, "16:00", {}), (D2, "16:00", UP)])
    assert r.trades == () and r.rejections[0]["source"] == "engine"
    assert r.proposals[-1]["status"] == "rejected:engine"


def closes_at(closes: list[str]) -> dict[str, str]:
    return {f"{(570 + i + 1) // 60:02d}:{(570 + i + 1) % 60:02d}": c for i, c in enumerate(closes)}


def test_bollinger_fade_sells_the_stretch_and_buys_back_at_the_horizon() -> None:
    params = {
        "timeframe": 1,
        "period": 3,
        "sigma_multiple": "1",
        "window_start": "09:31",
        "window_end": "14:00",
    }
    r = single_trade(
        "bollinger_reversion", params, closes_at(["100.0", "100.2", "100.0", "100.1", "101.0"])
    )
    (t,) = r.trades  # fresh +1.41 sigma at 09:35 -> SHORT; 20-minute horizon from the 09:36 fill
    assert (t.side, t.exit_reason) == ("SHORT", "horizon")
    assert t.entry_ts == local_ns(D2, "09:36") and t.exit_ts == local_ns(D2, "09:57")
    assert (t.entry_price, t.exit_price) == (Decimal("99.99"), Decimal("100.01"))
    assert t.commission == Decimal("1.70") and t.net_pnl == Decimal("-1.90")


def test_vwap_fade_sells_the_spike_once() -> None:
    params = {
        "window_start": "09:31",
        "window_end": "14:00",
        "sigma_multiple": "1.5",
        "min_bars": 3,
    }
    spike = ["100.0", "100.2", "99.8", "100.1", "99.9", "100.0", "100.1", "103.0"]
    r = single_trade("vwap_reversion", params, closes_at(spike))
    (t,) = r.trades
    assert t.side == "SHORT" and t.entry_ts == local_ns(D2, "09:39")
    assert t.exit_reason == "horizon" and r.reconciliation["ok"] and len(r.proposals) == 1


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_every_strategy_runs_the_full_path_and_reconciles(strategy: str) -> None:
    r = run_backtest(small(strategy))
    assert r.metrics["trades"] > 0 and r.reconciliation["ok"] and r.open_at_end is None
    assert r.engine["orders"] == 2 * r.metrics["trades"]
    assert all(t.exit_ts > t.entry_ts and t.quantity > 0 for t in r.trades)
    assert r.results_sha256 == run_backtest(small(strategy)).results_sha256
