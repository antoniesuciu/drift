"""Virtual portfolios: continuation must equal an uninterrupted run, or be refused."""

import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pyarrow as pa
import pytest
from research_helpers import FIRST, LAST, MIDDLE, NEXT, PLUGIN, PRECISE, SOURCE, job, settings

from drift.backtest.config import STRATEGIES
from drift.backtest.data import SyntheticSpec
from drift.backtest.registry import load_plugins
from drift.data.model import DataError
from drift.research.executors import ProcessExecutor, SequentialExecutor
from drift.research.portfolios import PortfolioBook
from drift.research.runner import run_batch
from drift.research.sources import SyntheticSource
from drift.research.store import ResultStore

load_plugins(PLUGIN)


@pytest.fixture
def store(tmp_path: Path) -> ResultStore:
    return ResultStore(tmp_path / "store")


def advance(store: ResultStore, name: str, end: str, start: str | None = None, **kwargs):
    book = PortfolioBook(store)
    source = kwargs.pop("source", SOURCE)
    plan = book.plan(name, source, start=start, end=end, plugins=PLUGIN, **kwargs)
    outcome = run_batch([plan], SequentialExecutor(), store, label="test").outcomes[0]
    if outcome.status == "completed":
        book.commit(plan, outcome)
    return outcome


def open_portfolio(store: ResultStore, strategy: str, name: str = "book", *overrides: str):
    return PortfolioBook(store).create(name, strategy, settings(strategy, *overrides))


def without(table: pa.Table, *columns: str) -> pa.Table:
    return table.drop_columns([c for c in columns if c in table.column_names])


def uninterrupted(store: ResultStore, strategy: str, *overrides: str) -> str:
    planned = job(store.root, strategy, *overrides)
    batch = run_batch([planned], SequentialExecutor(), store, label="whole")
    outcome = batch.outcomes[0]
    assert outcome.status == "completed", outcome.error
    return outcome.run_id


def segments(store: ResultStore, name: str = "book") -> list[str]:
    return [s["run_id"] for s in PortfolioBook(store).get(name).segments]


# Defaults keep most rules session-local, so the last cases force state across the boundary:
# ORB's multi-session volume and range lookbacks.
CASES = [(strategy, ()) for strategy in STRATEGIES] + [
    ("orb", ("params.rvol_min=0.5", "params.rvol_lookback=3", "params.prior_tr_below_atr=2")),
]


@pytest.mark.parametrize("strategy,overrides", CASES)
def test_a_segmented_portfolio_equals_one_uninterrupted_run(
    store: ResultStore, strategy: str, overrides: tuple[str, ...]
) -> None:
    whole = uninterrupted(store, strategy, *overrides)
    open_portfolio(store, strategy, "book", *overrides)
    assert advance(store, "book", MIDDLE, FIRST).status == "completed"
    assert advance(store, "book", LAST).status == "completed"
    runs = segments(store)
    assert len(runs) == 2
    ids = ("run_id", "trade_id")
    for name, ignored in (("trades", ids), ("equity", ids), ("fills", ("run_id", "order_number"))):
        split = without(store.table(name, runs), *ignored)
        expected = without(store.table(name, [whole]), *ignored)
        assert split.equals(expected), f"{name} differ"
    outcomes = ("order_number", "run_id", "submitted_ts")
    assert without(store.table("orders", runs), *outcomes).equals(
        without(store.table("orders", [whole]), *outcomes)
    )
    assert (
        store.table("proposals", runs)
        .column("proposal_id")
        .equals(store.table("proposals", [whole]).column("proposal_id"))
    )
    assert PortfolioBook(store).report("book")["metrics"] == store.manifest(whole)["metrics"]
    assert store.table("trades", runs).num_rows > 0


def test_sub_penny_fills_keep_the_same_cash_as_an_uninterrupted_run(store: ResultStore) -> None:
    """The engine books whole cents per fill, so a segment must restart from exactly that."""
    planned = replace(job(store.root, "reversal"), source=PRECISE)
    whole = run_batch([planned], SequentialExecutor(), store, label="whole").outcomes[0].run_id
    open_portfolio(store, "reversal")
    advance(store, "book", MIDDLE, FIRST, source=PRECISE)
    advance(store, "book", LAST, source=PRECISE)
    ignored = ("run_id", "trade_id")
    assert without(store.table("equity", segments(store)), *ignored).equals(
        without(store.table("equity", [whole]), *ignored)
    )
    report = PortfolioBook(store).report("book")
    assert report["metrics"] == store.manifest(whole)["metrics"]
    balance = store.manifest(whole)["reconciliation"]["engine_balance"]
    assert Decimal(report["cash"]) == Decimal(balance) == Decimal(report["equity"])


def test_three_segments_with_a_weekend_boundary_still_match(store: ResultStore) -> None:
    whole = uninterrupted(store, "reversal")
    open_portfolio(store, "reversal")
    advance(store, "book", "2022-03-11", FIRST)  # a Friday: the next session is after a weekend
    advance(store, "book", "2022-03-16")
    advance(store, "book", LAST)
    assert without(store.table("trades", segments(store)), "run_id", "trade_id").equals(
        without(store.table("trades", [whole]), "run_id", "trade_id")
    )


def test_cash_and_high_water_carry_across_segments(store: ResultStore) -> None:
    open_portfolio(store, "reversal")
    advance(store, "book", MIDDLE, FIRST)
    advance(store, "book", LAST)
    first, second = PortfolioBook(store).get("book").segments
    assert second["start_cash"] == first["end_cash"] != Decimal("20000")
    assert second["parent_run_id"] == first["run_id"]
    assert second["start_date"] == NEXT and second["trades_total"] > first["trades_total"]
    manifest = store.manifest(second["run_id"])
    assert manifest["data"]["replayed_candles"] > 0
    assert manifest["config"]["capital"] == str(first["end_cash"])


def test_trades_are_never_duplicated_and_stay_numbered(store: ResultStore) -> None:
    open_portfolio(store, "reversal")
    advance(store, "book", MIDDLE, FIRST)
    advance(store, "book", LAST)
    with store.connect() as db:
        total, distinct, proposals, low, high = db.execute(
            "SELECT count(*), count(DISTINCT trade_id), count(DISTINCT proposal_id),"
            " min(number), max(number) FROM portfolio_trades"
        ).fetchone()
    assert total == distinct == proposals == high and low == 1


def test_a_covered_period_cannot_be_simulated_again(store: ResultStore) -> None:
    open_portfolio(store, "orb")
    advance(store, "book", MIDDLE, FIRST)
    book = PortfolioBook(store)
    with pytest.raises(DataError, match="already covers"):
        book.plan("book", SOURCE, start=None, end=MIDDLE, plugins=PLUGIN)
    with pytest.raises(DataError, match="already covers"):
        book.plan("book", SOURCE, start=None, end=FIRST, plugins=PLUGIN)
    assert len(book.get("book").segments) == 1


def test_a_gap_cannot_even_be_requested(store: ResultStore) -> None:
    open_portfolio(store, "orb")
    advance(store, "book", MIDDLE, FIRST)
    with pytest.raises(DataError, match="starts where the portfolio stopped"):
        PortfolioBook(store).plan("book", SOURCE, start="2022-03-18", end=LAST, plugins=PLUGIN)


def test_a_first_segment_needs_a_start(store: ResultStore) -> None:
    open_portfolio(store, "orb")
    with pytest.raises(DataError, match="needs a start"):
        PortfolioBook(store).plan("book", SOURCE, start=None, end=LAST, plugins=PLUGIN)


def test_two_racing_segments_commit_at_most_once(store: ResultStore) -> None:
    open_portfolio(store, "orb")
    book = PortfolioBook(store)
    plans = [book.plan("book", SOURCE, start=FIRST, end=MIDDLE) for _ in range(2)]
    batch = run_batch(plans, SequentialExecutor(), store, label="race")
    book.commit(plans[0], batch.outcomes[0])
    with pytest.raises(DataError, match="moved on"):
        book.commit(plans[1], batch.outcomes[1])
    assert len(book.get("book").segments) == 1


def test_a_crash_between_publish_and_commit_recovers_without_duplicates(store: ResultStore) -> None:
    open_portfolio(store, "orb")
    book = PortfolioBook(store)
    lost = book.plan("book", SOURCE, start=FIRST, end=MIDDLE, plugins=PLUGIN)
    assert run_batch([lost], SequentialExecutor(), store, label="lost").ok  # never committed
    retried = advance(store, "book", MIDDLE, FIRST)
    assert retried.reused and len(book.get("book").segments) == 1
    with store.connect() as db:
        assert db.execute("SELECT count(*) FROM runs").fetchone() == (1,)


def test_a_failed_segment_leaves_the_portfolio_untouched(store: ResultStore) -> None:
    open_portfolio(store, "broken")
    assert advance(store, "book", MIDDLE, FIRST).status == "failed"
    assert PortfolioBook(store).get("book").segments == ()


def test_an_open_position_stops_the_portfolio(store: ResultStore) -> None:
    open_portfolio(store, "holder")
    advance(store, "book", MIDDLE, FIRST)
    book = PortfolioBook(store)
    head = book.get("book").segments[-1]
    assert not head["continuable"] and "open position" in head["stop_reason"]
    assert Decimal(book.report("book")["position"]) > 0
    with pytest.raises(DataError, match="cannot continue: open position"):
        book.plan("book", SOURCE, start=None, end=LAST, plugins=PLUGIN)


def test_an_order_live_across_the_boundary_stops_the_portfolio(store: ResultStore) -> None:
    open_portfolio(store, "late_order")
    advance(store, "book", MIDDLE, FIRST)
    book = PortfolioBook(store)
    assert "live across" in book.get("book").segments[-1]["stop_reason"]
    with pytest.raises(DataError, match="cannot continue"):
        book.plan("book", SOURCE, start=None, end=LAST, plugins=PLUGIN)


def test_a_non_replayable_strategy_cannot_resume(store: ResultStore) -> None:
    open_portfolio(store, "coin")
    assert advance(store, "book", MIDDLE, FIRST).status == "completed"
    with pytest.raises(DataError, match="not replayable"):
        PortfolioBook(store).plan("book", SOURCE, start=None, end=LAST, plugins=PLUGIN)


def test_revised_market_history_refuses_to_resume(store: ResultStore) -> None:
    open_portfolio(store, "orb")
    advance(store, "book", MIDDLE, FIRST)
    spec = SyntheticSpec(8, "2022-03-07", 12, Decimal("100.00"), 4, 2, 60, 1000, 1)
    revised = SyntheticSource(spec, SOURCE.instrument)
    outcome = advance(store, "book", LAST, source=revised)
    assert outcome.status == "failed" and "market history changed" in outcome.error
    assert len(PortfolioBook(store).get("book").segments) == 1


def test_a_code_change_must_be_accepted_and_is_recorded(store: ResultStore, monkeypatch) -> None:
    from drift.research import runner

    open_portfolio(store, "orb")
    advance(store, "book", MIDDLE, FIRST)
    real = runner.software()
    monkeypatch.setattr(runner, "software", lambda: real | {"nautilus": "another"})
    with pytest.raises(DataError, match="code changed"):
        PortfolioBook(store).plan("book", SOURCE, start=None, end=LAST, plugins=PLUGIN)
    advance(store, "book", LAST, accept_code_change=True)
    assert PortfolioBook(store).get("book").segments[-1]["code_changed"] is True


def test_editing_a_plugin_counts_as_a_code_change(
    store: ResultStore, tmp_path, monkeypatch
) -> None:
    plugin = tmp_path / "edited_plugin.py"
    plugin.write_text("VERSION = 1\n")
    monkeypatch.syspath_prepend(tmp_path)
    open_portfolio(store, "orb")
    book = PortfolioBook(store)
    plan = book.plan("book", SOURCE, start=FIRST, end=MIDDLE, plugins=("edited_plugin",))
    outcome = run_batch([plan], SequentialExecutor(), store, label="t").outcomes[0]
    book.commit(plan, outcome)
    assert "edited_plugin" in store.manifest(outcome.run_id)["plugins"]
    plugin.write_text("VERSION = 2\n")
    with pytest.raises(DataError, match="code changed"):
        book.plan("book", SOURCE, start=None, end=LAST, plugins=("edited_plugin",))


def test_parameter_changes_apply_forward_and_history_is_kept(store: ResultStore) -> None:
    open_portfolio(store, "reversal")
    book = PortfolioBook(store)
    advance(store, "book", MIDDLE, FIRST)
    version = book.configure("book", [(["execution", "slippage_bps"], "50")])
    advance(store, "book", LAST)
    first, second = book.get("book").segments
    assert (version, first["config_version"], second["config_version"]) == (2, 1, 2)
    assert store.manifest(first["run_id"])["config"]["costs"]["slippage_bps"] == "1"
    assert store.manifest(second["run_id"])["config"]["costs"]["slippage_bps"] == "50"
    with store.connect() as db:
        stored = db.execute(
            "SELECT version, settings_json FROM portfolio_configs ORDER BY version"
        ).fetchall()
    assert [json.loads(s)["execution"]["slippage_bps"] for _, s in stored] == ["1", "50"]


def test_a_changed_parameter_replays_under_the_new_value(store: ResultStore) -> None:
    open_portfolio(store, "orb")
    book = PortfolioBook(store)
    advance(store, "book", MIDDLE, FIRST)
    book.configure("book", [(["params", "horizon_seconds"], 900)])
    outcome = advance(store, "book", LAST)
    assert outcome.status == "completed", outcome.error
    held = store.table("trades", [outcome.run_id]).column("held_seconds").to_pylist()
    assert held and max(held) <= 960  # 900 s, then the first open strictly after it


def test_configuration_rejects_no_ops_and_invalid_values(store: ResultStore) -> None:
    open_portfolio(store, "orb")
    book = PortfolioBook(store)
    with pytest.raises(DataError, match="no setting changed"):
        book.configure("book", [(["execution", "slippage_bps"], "1")])
    with pytest.raises(DataError):
        book.configure("book", [(["execution", "slippage_bps"], "-1")])
    with pytest.raises(DataError):
        book.configure("book", [(["params", "mystery"], 1)])
    assert len(book.get("book").configs) == 1


def test_experiments_stay_out_of_portfolio_views(store: ResultStore) -> None:
    whole = uninterrupted(store, "orb")
    open_portfolio(store, "orb")
    advance(store, "book", MIDDLE, FIRST)
    book = PortfolioBook(store)
    orphan = book.plan("book", SOURCE, start=None, end=LAST, plugins=PLUGIN)
    assert run_batch([orphan], SequentialExecutor(), store, label="uncommitted").ok
    with store.connect() as db:
        kinds = db.execute("SELECT kind, count(*) FROM runs GROUP BY 1 ORDER BY 1").fetchall()
        attached = db.execute("SELECT DISTINCT run_id FROM portfolio_equity").fetchall()
    assert kinds == [("experiment", 1), ("portfolio", 2)]
    assert attached == [(segments(store)[0],)] and whole not in attached[0]


def test_independent_portfolios_advance_concurrently_and_stay_separate(store: ResultStore) -> None:
    book = PortfolioBook(store)
    for name, strategy, capital in (("a", "orb", "20000"), ("b", "orb", "35000")):
        book.create(name, strategy, settings(strategy, capital=capital))
    plans = [book.plan(n, SOURCE, start=FIRST, end=MIDDLE) for n in ("a", "b")]
    batch = run_batch(plans, ProcessExecutor(2), store, label="both")
    assert batch.ok
    for plan, outcome in zip(plans, batch.outcomes, strict=True):
        book.commit(plan, outcome)
    a, b = book.report("a"), book.report("b")
    assert a["initial_capital"] != b["initial_capital"] and a["cash"] != b["cash"]


def test_portfolio_identity_is_guarded(store: ResultStore) -> None:
    open_portfolio(store, "orb")
    book = PortfolioBook(store)
    with pytest.raises(DataError, match="already exists"):
        open_portfolio(store, "orb")
    with pytest.raises(DataError, match="no such portfolio"):
        book.get("absent")
    for bad in ("../escape", "_schema", ""):
        with pytest.raises(DataError):
            book.get(bad)
    with pytest.raises(DataError):
        book.create("bad-settings", "orb", settings("orb", "risk.max_notional=0"))
    assert book.names() == ["book"]


def test_report_of_a_new_portfolio_is_just_its_capital(store: ResultStore) -> None:
    open_portfolio(store, "orb")
    report = PortfolioBook(store).report("book")
    assert (report["equity"], report["through"], report["segments"]) == ("20000.000000", None, [])
    assert report["continuable"] is True


def test_run_ids_differ_between_a_portfolio_and_an_experiment(store: ResultStore) -> None:
    whole = uninterrupted(store, "orb")
    open_portfolio(store, "orb")
    assert advance(store, "book", LAST, FIRST).run_id != whole
