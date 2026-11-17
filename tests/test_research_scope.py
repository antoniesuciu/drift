"""Windows, the research split, costs, and the path from the verified archive to a run."""

import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest
from helpers import make_config, scripted_market
from research_helpers import EQUITY, PLUGIN, ScriptedSource, job, settings
from test_history import archive

from drift.backtest.config import Costs
from drift.backtest.data import MarketData
from drift.backtest.engine import run_on
from drift.backtest.registry import load_plugins
from drift.backtest.risk import Sizing
from drift.data.model import DataError
from drift.research.executors import SequentialExecutor
from drift.research.portfolios import PortfolioBook
from drift.research.runner import RunJob, attempt, run_batch
from drift.research.scope import Interval, authorize
from drift.research.settings import (
    apply_overrides,
    cost_label,
    default_settings,
    flatten,
    parse_override,
)
from drift.research.sources import ArchiveSource
from drift.research.store import ResultStore

JULY = Interval("2021-07-16", "2021-07-21")
ROWS = tuple((day, "16:00", {}) for day in ("2022-03-07", "2022-03-08", "2022-03-09", "2022-03-10"))


def test_a_year_or_explicit_dates_select_an_interval() -> None:
    assert Interval.select(2021, None, None) == Interval("2021-01-01", "2021-12-31")
    assert Interval.select(None, "2021-02-01", "2021-03-01").end == "2021-03-01"


@pytest.mark.parametrize(
    "year,start,end",
    [
        (None, None, None),
        (2021, "2021-01-01", None),
        (None, "2021-01-01", None),
        (None, "2021-03-01", "2021-01-01"),
        (None, "2021-02-30", "2021-03-01"),
        (None, "20210101", "20210201"),
    ],
)
def test_bad_intervals_are_refused(year, start, end) -> None:
    with pytest.raises(DataError):
        Interval.select(year, start, end)


def test_development_is_open() -> None:
    assert authorize(Interval("2020-01-01", "2022-12-31")) == ("development",)


def test_validation_needs_an_explicit_opt_in() -> None:
    with pytest.raises(DataError, match="allow-validation"):
        authorize(Interval("2023-01-01", "2023-12-31"))
    window = Interval("2022-06-01", "2023-06-30")
    assert authorize(window, allow_validation=True) == ("development", "validation")


@pytest.mark.parametrize(
    "window",
    [("2024-01-01", "2024-12-31"), ("2025-03-01", "2025-03-31"), ("2022-01-01", "2024-01-02")],
)
def test_holdout_cannot_be_unlocked(window) -> None:
    with pytest.raises(DataError, match="holdout"):
        authorize(Interval(*window), allow_validation=True)


def historical(day: str) -> MarketData:
    market = scripted_market(EQUITY, [(day, "16:00", {})])
    return MarketData.build(
        EQUITY, market.calendar, market.candles, source_ref="a" * 64, source_feed="sip"
    )


def test_the_engine_itself_refuses_later_years_by_default() -> None:
    config = make_config("itsm")
    for day in ("2023-03-07", "2024-03-07"):
        with pytest.raises(DataError, match="integrity only"):
            run_on(config, historical(day))


def test_no_caller_can_evaluate_holdout() -> None:
    every = ("development", "validation", "holdout")
    with pytest.raises(DataError, match="integrity only"):
        run_on(make_config("itsm"), historical("2024-03-07"), evaluate=every)


def test_a_window_opt_in_reaches_the_engine_gate() -> None:
    with pytest.raises(DataError, match="data source identity|historical data requires"):
        run_on(make_config("itsm"), historical("2023-03-07"), evaluate=("validation",))


def test_replay_candles_do_not_count_as_evaluation() -> None:
    market = scripted_market(EQUITY, [("2022-12-29", "16:00", {}), ("2022-12-30", "16:00", {})])
    data = MarketData.build(
        EQUITY, market.calendar, market.candles, source_ref="a" * 64, source_feed="sip"
    )
    start = next(c.start for c in data.candles if c.day == "2022-12-30")
    with pytest.raises(DataError, match="data source identity|historical data requires"):
        run_on(make_config("itsm"), data, trade_from=start)  # past the split gate


def test_bps_costs_are_rounded_against_the_trader() -> None:
    costs = make_config("itsm").costs
    bps = replace(costs, half_spread_ticks=0, half_spread_bps=Decimal("1"), slippage_bps=Decimal(1))
    assert bps.offset(Decimal("750"), Decimal("0.01")) == Decimal("0.15")
    ticks = replace(costs, half_spread_ticks=2, slippage_ticks=1)
    assert ticks.offset(Decimal("750"), Decimal("0.01")) == Decimal("0.03")


def test_negative_bps_are_refused() -> None:
    with pytest.raises(DataError):
        Costs(0, 0, 0, Decimal(0), Decimal(0), None, Decimal(0), Decimal(-1))


def test_equity_fraction_sizes_from_the_current_balance() -> None:
    sizing = Sizing("equity_fraction", Decimal("0.95"))
    assert sizing.quantity(Decimal(100), Decimal(1), Decimal(1), Decimal(20000)) == 190
    assert sizing.quantity(Decimal(100), Decimal(1), Decimal(1), Decimal(10000)) == 95
    assert sizing.quantity(Decimal(100), Decimal(1), Decimal(1)) == 0
    with pytest.raises(DataError):
        Sizing("equity_fraction", Decimal("1.5"))


def test_defaults_are_twenty_thousand_and_long_only_with_real_costs() -> None:
    chosen = default_settings("orb")
    assert chosen["capital"] == "20000" and chosen["params"]["allow_short"] is False
    assert cost_label(chosen["execution"]) == "base"
    assert Decimal(chosen["execution"]["per_unit"]) > 0
    assert default_settings("orb", capital="50000")["risk"]["max_session_loss"] == "2500"


def test_zero_costs_exist_only_on_request() -> None:
    assert cost_label(default_settings("orb", costs="zero")["execution"]) == "zero"
    changed = settings("orb", "execution.slippage_bps=9")
    assert cost_label(changed["execution"]) == "custom"
    with pytest.raises(DataError):
        default_settings("orb", costs="free")


def test_overrides_target_all_strategies_or_one() -> None:
    pairs = [parse_override("execution.slippage_bps=2"), parse_override("orb.params.rvol_min=1.5")]
    orb = apply_overrides(default_settings("orb"), "orb", pairs)
    trend = apply_overrides(default_settings("trend"), "trend", pairs)
    assert orb["execution"]["slippage_bps"] == trend["execution"]["slippage_bps"] == 2
    assert orb["params"]["rvol_min"] == "1.5" and "rvol_min" not in trend["params"]


@pytest.mark.parametrize("bad", ["capital=5", "nonsense.x=1", "execution=1", "orb=1"])
def test_unknown_override_paths_are_refused(bad: str) -> None:
    with pytest.raises(DataError):
        apply_overrides(default_settings("orb"), "orb", [parse_override(bad)])


def test_a_settings_file_and_overrides_share_one_rule() -> None:
    assert flatten({"execution": {"slippage_bps": "2"}, "orb": {"params": {"rvol_min": "2"}}}) == [
        (["execution", "slippage_bps"], "2"),
        (["orb", "params", "rvol_min"], "2"),
    ]


def test_exit_overrides_extend_the_strategy_policy(tmp_path: Path) -> None:
    run = job(tmp_path, "orb", 'exit.stop={"kind":"percent","value":"1"}')
    outcome = attempt(run)
    assert outcome.status == "completed", outcome.error
    policy = ResultStore(tmp_path).manifest(outcome.run_id)["config"]["strategy"]["exit"]
    assert policy["stop"] == {"kind": "percent", "value": "1"}
    assert policy["horizon_seconds"] == 1800 and policy["exit_on_opposite"] is False


def archive_job(root: Path, store: Path, strategy: str = "itsm", *overrides: str) -> RunJob:
    return RunJob(
        strategy,
        settings(strategy, *overrides),
        JULY,
        ArchiveSource(root),
        store,
        authorize(JULY),
    )


def test_archive_loads_a_verified_window_and_its_splits(tmp_path: Path) -> None:
    source = ArchiveSource(archive(tmp_path))
    source.verify(JULY)
    piece = source.load(JULY)
    assert len(piece.data.candles) == 1560 and piece.data.source_feed == "sip"
    assert piece.splits == (("2021-07-20", "4"),) and piece.gaps == ()
    assert piece.data.instrument.precision == 6
    assert len(source.load(Interval("2021-07-19", "2021-07-20")).data.candles) == 780


def test_archive_refuses_months_it_does_not_hold(tmp_path: Path) -> None:
    source = ArchiveSource(archive(tmp_path))
    with pytest.raises(DataError, match="no data for 2021-08"):
        source.load(Interval("2021-07-16", "2021-08-31"))
    with pytest.raises(DataError, match="2020–2025"):
        source.load(Interval("2019-12-01", "2020-01-31"))


def test_archive_refuses_tampered_bars(tmp_path: Path) -> None:
    root = archive(tmp_path)
    index = json.loads((root / "index.json").read_text())
    bars = root / index["months"][0]["dataset"] / "bars.parquet"
    bars.write_bytes(bars.read_bytes()[:-20] + b"0" * 20)
    with pytest.raises(DataError, match="differs from its manifest"):
        ArchiveSource(root).load(JULY)


def test_a_run_on_the_archive_records_real_lineage(tmp_path: Path) -> None:
    run = archive_job(archive(tmp_path), tmp_path / "store")
    outcome = attempt(run)
    assert outcome.status == "completed", outcome.error
    manifest = ResultStore(tmp_path / "store").manifest(outcome.run_id)
    assert manifest["research_role"] == "development" and manifest["synthetic"] is False
    assert manifest["data"]["feed"] == "sip" and manifest["data"]["missing_minutes"] == 0
    assert manifest["config"]["strategy"]["params"]["splits"] == [["2021-07-20", "4"]]


def test_a_position_that_could_cross_a_split_is_refused(tmp_path: Path) -> None:
    run = archive_job(
        archive(tmp_path),
        tmp_path / "store",
        "itsm",
        "exit.flatten_lead_seconds=null",
        "exit.horizon_seconds=7200",
    )
    outcome = attempt(run)
    assert outcome.status == "failed" and "cross a split" in outcome.error


@pytest.mark.parametrize(
    "strategy,overrides",
    [
        ("orb", ("params.rvol_min=2",)),
        ("orb", ("params.prior_tr_below_atr=2",)),
    ],
)
def test_history_that_would_compare_across_a_split_is_refused(
    tmp_path: Path, strategy: str, overrides: tuple[str, ...]
) -> None:
    outcome = attempt(archive_job(archive(tmp_path), tmp_path / "store", strategy, *overrides))
    assert outcome.status == "failed" and "split-neutral" in outcome.error


@pytest.mark.parametrize("strategy", ["orb", "reversal", "trend", "vwap_reversion"])
def test_session_local_strategies_may_cross_a_split(tmp_path: Path, strategy: str) -> None:
    outcome = attempt(archive_job(archive(tmp_path), tmp_path / "store", strategy))
    assert outcome.status == "completed", outcome.error


def test_a_strategy_must_claim_split_safety(tmp_path: Path) -> None:
    load_plugins(PLUGIN)
    outcome = attempt(archive_job(archive(tmp_path), tmp_path / "store", "probe_ml"))
    assert outcome.status == "failed" and "split-neutral" in outcome.error


def test_stored_gaps_count_only_the_traded_window(tmp_path: Path) -> None:
    source = replace(ScriptedSource(ROWS), gaps=(("2022-03-07", 14), ("2022-03-09", 3)))
    store = ResultStore(tmp_path)
    book = PortfolioBook(store)
    book.create("gaps", "orb", settings("orb"))
    for start, end in (("2022-03-07", "2022-03-08"), (None, "2022-03-10")):
        plan = book.plan("gaps", source, start=start, end=end)
        batch = run_batch([plan], SequentialExecutor(), store, label="gaps")
        book.commit(plan, batch.outcomes[0])
    with store.connect() as db:
        rows = db.execute("SELECT missing_minutes FROM runs ORDER BY segment").fetchall()
    assert rows == [(14,), (3,)]
