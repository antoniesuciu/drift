"""What a run leaves behind: immutable files a dashboard can query with plain SQL."""

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import duckdb
import pyarrow.parquet as pq
import pytest
from research_helpers import FIRST, ScriptedSource, job, settings

from drift.backtest.config import STRATEGIES
from drift.backtest.engine import run_on
from drift.data.model import DataError
from drift.research import metrics
from drift.research import store as store_module
from drift.research.executors import SequentialExecutor
from drift.research.records import build_record
from drift.research.runner import RunJob, attempt, run_batch
from drift.research.scope import Interval
from drift.research.settings import backtest_config
from drift.research.store import ResultStore

DROP = {
    "10:00": ("100.00", "101.00", "100.00", "101.00"),
    "15:00": ("100.00", "100.50", "100.00", "100.50"),
    "15:30": ("100.50", "101.00", "100.50", "101.00"),
    "15:40": ("100.00", "100.00", "90.00", "90.00"),
    "15:50": ("90.00", "96.00", "90.00", "95.00"),
}


def run_all(root: Path, *names: str):
    store = ResultStore(root)
    jobs = [job(root, name) for name in names or STRATEGIES]
    return store, run_batch(jobs, SequentialExecutor(), store, label="test")


def test_every_view_exists_and_is_empty_in_a_new_store(tmp_path: Path) -> None:
    views = "runs trades orders fills equity proposals metrics comparison batches".split()
    views += "portfolios portfolio_configs portfolio_segments portfolio_trades".split()
    with ResultStore(tmp_path).connect() as db:
        for view in (*views, "portfolio_equity"):
            assert db.execute(f"SELECT count(*) FROM {view}").fetchone() == (0,)


def test_comparison_ranks_strategies_on_profit_risk_and_frequency(tmp_path: Path) -> None:
    store, batch = run_all(tmp_path)
    assert batch.ok
    with store.connect() as db:
        rows = db.execute(
            "SELECT strategy, net_pnl, sharpe, max_drawdown_pct, trades, trades_per_session"
            " FROM comparison ORDER BY net_pnl DESC"
        ).fetchall()
    assert {r[0] for r in rows} == set(STRATEGIES) and len(rows) == len(STRATEGIES)
    assert [r[1] for r in rows] == sorted((r[1] for r in rows), reverse=True)
    assert any(r[4] > 0 and r[5] > 0 and r[3] > 0 for r in rows)


def test_stored_money_reconciles_across_tables(tmp_path: Path) -> None:
    store, _ = run_all(tmp_path, "reversal")
    with store.connect() as db:
        net, fees = db.execute("SELECT sum(net_pnl), sum(commission) FROM trades").fetchone()
        fill_fees = db.execute("SELECT sum(commission) FROM fills").fetchone()[0]
        last = db.execute("SELECT equity, cash FROM equity ORDER BY ts DESC LIMIT 1").fetchone()
        stored = dict(db.execute("SELECT metric, value FROM metrics").fetchall())
        orders, fills = db.execute(
            "SELECT (SELECT count(*) FROM orders), (SELECT count(*) FROM fills)"
        ).fetchone()
    assert fees == fill_fees and orders == fills > 0
    assert last == (Decimal("20000") + net, Decimal("20000") + net)
    assert stored["net_pnl"] == pytest.approx(float(net))
    assert stored["commissions"] == pytest.approx(float(fees))


def test_equity_marks_open_trades_so_drawdown_sees_intraday_losses(tmp_path: Path) -> None:
    source = ScriptedSource((("2022-03-07", "16:00", {}), ("2022-03-08", "16:00", DROP)))
    chosen = settings("itsm", "sizing.amount=1")
    window = Interval(FIRST, "2022-03-08")
    run = RunJob("itsm", chosen, window, source, tmp_path, ("synthetic",))
    outcome = attempt(run)
    assert outcome.status == "completed", outcome.error
    with ResultStore(tmp_path).connect() as db:
        peak, worst, position = db.execute(
            "SELECT max(high_water), max(drawdown), max(position) FROM equity"
        ).fetchone()
        last = db.execute("SELECT equity FROM equity ORDER BY ts DESC LIMIT 1").fetchone()[0]
    # Bought 200 at 100.02, paying 0.70. The 15:40 bar closes at 90.00, so marked equity is
    # 20,000 - 0.70 + 200 × (90.00 - 100.02) = 17,995.30, far below any realized balance.
    assert position == Decimal("200")
    assert worst == peak - Decimal("17995.30")
    assert last > Decimal("17995.30")  # the realized result recovers; a realized curve hides it


def test_repeating_a_run_reuses_it_and_logs_the_attempt(tmp_path: Path) -> None:
    store, first = run_all(tmp_path, "orb")
    second = run_batch([job(tmp_path, "orb")], SequentialExecutor(), store, label="again")
    assert first.outcomes[0].run_id == second.outcomes[0].run_id and second.outcomes[0].reused
    with store.connect() as db:
        assert db.execute("SELECT count(*) FROM runs").fetchone() == (1,)
        assert db.execute("SELECT count(DISTINCT batch_id) FROM batches").fetchone() == (2,)


def test_changing_any_input_changes_the_run_id(tmp_path: Path) -> None:
    first = attempt(job(tmp_path, "orb"))
    other = attempt(job(tmp_path, "orb", "execution.slippage_bps=9"))
    window = attempt(job(tmp_path, "orb", window=Interval(FIRST, "2022-03-15")))
    assert len({first.run_id, other.run_id, window.run_id}) == 3


def test_manifest_links_strategy_parameters_data_and_code(tmp_path: Path) -> None:
    store, batch = run_all(tmp_path, "orb")
    manifest = store.manifest(batch.outcomes[0].run_id)
    assert manifest["kind"] == "experiment" and manifest["strategy"] == "orb"
    assert manifest["config"]["strategy"]["params"]["allow_short"] is False
    assert len(manifest["data_sha256"]) == len(manifest["software"]["code_sha256"]) == 64
    assert manifest["cost_profile"] == "base" and manifest["research_role"] == "synthetic"
    assert set(manifest["inventory"]) >= {"trades.parquet", "equity.parquet", "run.parquet"}


def _record(root: Path):
    planned = job(root, "orb")
    piece = planned.source.load(planned.interval)
    config = backtest_config("orb", planned.settings, piece, name="x", capital="20000")
    result = run_on(config, piece.data)
    return build_record(
        "orb",
        planned.settings,
        planned.interval,
        ("synthetic",),
        None,
        config,
        piece,
        result,
        "c" * 64,
        {},
    )


def test_identical_inputs_with_different_results_are_refused(tmp_path: Path) -> None:
    store = ResultStore(tmp_path)
    record = _record(tmp_path)
    assert store.publish(record) is True and store.publish(record) is False
    lie = replace(record, manifest=record.manifest | {"results_sha256": "0" * 64})
    with pytest.raises(DataError, match="not reproducible"):
        store.publish(lie)


def test_a_failed_publish_leaves_nothing_visible(tmp_path: Path, monkeypatch) -> None:
    store = ResultStore(tmp_path)
    record = _record(tmp_path)

    def broken(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(store_module.pq, "write_table", broken)
    with pytest.raises(OSError):
        store.publish(record)
    assert not (tmp_path / "runs" / record.run_id).exists()
    assert list((tmp_path / "staging").iterdir()) == []


def test_tampered_results_are_detected(tmp_path: Path) -> None:
    store, batch = run_all(tmp_path, "reversal")
    run_id = batch.outcomes[0].run_id
    folder = tmp_path / "runs" / run_id
    table = pq.read_table(folder / "trades.parquet").slice(1)
    pq.write_table(table, folder / "trades.parquet")
    with pytest.raises(DataError, match="differs from its manifest"):
        store.table("trades", [run_id])
    (folder / "manifest.json").write_text("{}")
    with pytest.raises(DataError, match="commit marker"):
        store.manifest(run_id)


def test_run_ids_cannot_name_paths(tmp_path: Path) -> None:
    with pytest.raises(DataError, match="invalid run id"):
        ResultStore(tmp_path).manifest("../../etc/passwd")
    with pytest.raises(DataError, match="no such run"):
        ResultStore(tmp_path).manifest("0" * 24)


def test_any_duckdb_client_can_read_the_same_files(tmp_path: Path) -> None:
    _, batch = run_all(tmp_path, "reversal")
    pattern = f"{tmp_path}/runs/*/trades.parquet"
    count = (
        duckdb.connect()
        .execute("SELECT count(*) FROM read_parquet(?, union_by_name = true)", [pattern])
        .fetchone()[0]
    )
    assert count > 0 and batch.ok


def test_a_new_metric_needs_one_function(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(metrics, "_METRICS", list(metrics._METRICS))

    @metrics.metric
    def edge(frame: metrics.Frame) -> dict[str, float | None]:
        return {"trades_squared": float(len(frame.trades) ** 2)}

    store, batch = run_all(tmp_path, "orb")
    with store.connect() as db:
        value = db.execute("SELECT value FROM metrics WHERE metric = 'trades_squared'").fetchone()[
            0
        ]
        trades = db.execute("SELECT count(*) FROM trades").fetchone()[0]
        ranked = db.execute("SELECT trades_squared FROM comparison").fetchone()[0]
    assert value == ranked == trades**2 and batch.ok


def test_sharpe_matches_a_worked_example() -> None:
    closes = (101.0, 100.0, 102.0)
    frame = metrics.Frame(Decimal(100), (), closes, Decimal(1), 0.01, 1)
    # Returns +1%, -0.990099%, +2%: mean 0.669967%, sample deviation 1.522125%.
    assert metrics.risk(frame)["sharpe"] == pytest.approx(0.00669967 / 0.01522125 * 252**0.5)
    assert metrics.frequency(frame)["sessions"] == 3


def test_metrics_of_a_flat_run_are_undefined_not_zero() -> None:
    frame = metrics.Frame(Decimal(100), (), (100.0, 100.0), Decimal(0), 0.0, 1)
    measured = metrics.compute(frame)
    assert measured["sharpe"] is None and measured["win_rate"] is None
    assert measured["net_pnl"] == 0
