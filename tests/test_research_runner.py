"""Selecting, running and isolating strategies through `run_batch`."""

from decimal import Decimal
from pathlib import Path

import pytest
from research_helpers import FIRST, PLUGIN, SOURCE, ScriptedSource, job, settings

from drift.backtest.config import STRATEGIES
from drift.backtest.registry import load_plugins
from drift.data.model import DataError
from drift.research.executors import ProcessExecutor, SequentialExecutor, default_workers
from drift.research.runner import RunJob, attempt, run_batch
from drift.research.scope import Interval
from drift.research.store import ResultStore

load_plugins(PLUGIN)
UP = {"10:00": "101.00", "15:00": "100.50", "15:30": "101.00"}


def sequential(store: Path, jobs: list[RunJob]):
    return run_batch(jobs, SequentialExecutor(), ResultStore(store), label="test")


def test_concurrent_and_sequential_runs_agree_exactly(tmp_path: Path) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    one = sequential(a, [job(a, s) for s in STRATEGIES])
    two = run_batch(
        [job(b, s) for s in STRATEGIES], ProcessExecutor(3), ResultStore(b), label="test"
    )
    assert one.ok and two.ok
    assert [o.run_id for o in one.outcomes] == [o.run_id for o in two.outcomes]
    for first, second in zip(one.outcomes, two.outcomes, strict=True):
        left, right = ResultStore(a).manifest(first.run_id), ResultStore(b).manifest(second.run_id)
        assert left["results_sha256"] == right["results_sha256"]
    assert (
        ResultStore(a)
        .table("trades", [one.outcomes[0].run_id])
        .equals(ResultStore(b).table("trades", [two.outcomes[0].run_id]))
    )


def test_a_strategy_run_alone_matches_the_same_strategy_in_a_batch(tmp_path: Path) -> None:
    together = sequential(tmp_path, [job(tmp_path, s) for s in ("orb", "reversal", "trend")])
    alone = sequential(tmp_path, [job(tmp_path, "reversal")])
    assert alone.outcomes[0].run_id == together.outcomes[1].run_id and alone.outcomes[0].reused


def test_each_strategy_gets_its_own_capital(tmp_path: Path) -> None:
    batch = sequential(tmp_path, [job(tmp_path, s) for s in ("trend", "reversal")])
    store = ResultStore(tmp_path)
    with store.connect() as db:
        rows = db.execute("SELECT strategy, capital FROM runs ORDER BY strategy").fetchall()
    assert rows == [("reversal", Decimal("20000")), ("trend", Decimal("20000"))]
    assert batch.ok


def test_interval_bounds_every_trade_and_equity_row(tmp_path: Path) -> None:
    window = Interval("2022-03-09", "2022-03-11")
    outcome = sequential(tmp_path, [job(tmp_path, "reversal", window=window)]).outcomes[0]
    with ResultStore(tmp_path).connect() as db:
        days = db.execute(
            "SELECT min(session_date), max(session_date), count(DISTINCT session_date) FROM equity"
        ).fetchone()
        trades = db.execute("SELECT count(*) FROM trades").fetchone()[0]
    assert days == ("2022-03-09", "2022-03-11", 3) and trades > 0 and outcome.status == "completed"


def test_uncovered_interval_fails_instead_of_running_on_less_data(tmp_path: Path) -> None:
    late = Interval("2022-03-21", "2022-12-31")
    outcome = attempt(job(tmp_path, "orb", window=late))
    assert outcome.status == "failed" and "does not cover" in outcome.error


@pytest.mark.parametrize(
    "executor", [SequentialExecutor(), ProcessExecutor(2)], ids=["sequential", "process"]
)
def test_an_exception_costs_only_its_own_strategy(tmp_path: Path, executor) -> None:
    jobs = [job(tmp_path, s) for s in ("trend", "broken", "orb")]
    batch = run_batch(jobs, executor, ResultStore(tmp_path), label="test")
    assert [o.status for o in batch.outcomes] == ["completed", "failed", "completed"]
    assert batch.outcomes[1].error_type == "RuntimeError" and not batch.ok
    with ResultStore(tmp_path).connect() as db:
        stored = db.execute("SELECT strategy FROM runs ORDER BY strategy").fetchall()
        log = db.execute(
            "SELECT strategy, status, error_type FROM batches ORDER BY position"
        ).fetchall()
    assert stored == [("orb",), ("trend",)]
    assert log[1] == ("broken", "failed", "RuntimeError")


def test_a_dead_process_costs_only_its_own_strategy(tmp_path: Path) -> None:
    jobs = [job(tmp_path, s) for s in ("crash", "trend")]
    batch = run_batch(jobs, ProcessExecutor(2), ResultStore(tmp_path), label="test")
    crashed, survivor = batch.outcomes
    assert (crashed.status, crashed.error_type, crashed.error) == (
        "failed",
        "WorkerDied",
        "exit code 13",
    )
    assert survivor.status == "completed"


def test_a_hung_strategy_is_stopped_at_its_time_limit(tmp_path: Path) -> None:
    jobs = [job(tmp_path, s) for s in ("hang", "orb")]
    batch = run_batch(jobs, ProcessExecutor(2, 15), ResultStore(tmp_path), label="test")
    assert batch.outcomes[0].error_type == "Timeout" and batch.outcomes[1].status == "completed"


def test_workers_limit_how_many_strategies_overlap(tmp_path: Path, monkeypatch) -> None:
    log = tmp_path / "overlap.log"
    monkeypatch.setenv("DRIFT_PROBE", str(log))
    jobs = [job(tmp_path, "sleeper", capital=c) for c in ("20000", "20001", "20002", "20003")]
    assert run_batch(jobs, ProcessExecutor(2), ResultStore(tmp_path), label="test").ok
    spans = [tuple(map(float, line.split())) for line in log.read_text().splitlines()]
    overlaps = [sum(a <= t < b for a, b in spans) for t, _ in spans]
    assert len(spans) == 4 and max(overlaps) == 2


def test_a_new_family_runs_without_touching_the_runner(tmp_path: Path) -> None:
    jobs = [job(tmp_path, "probe_ml", "params.entry_valid_seconds=120")]
    batch = run_batch(jobs, ProcessExecutor(1), ResultStore(tmp_path), label="test")
    assert batch.ok
    with ResultStore(tmp_path).connect() as db:
        assert db.execute("SELECT family, kind FROM runs").fetchall() == [("ML", "experiment")]
        assert db.execute("SELECT count(*) FROM trades").fetchone()[0] > 0


def test_results_match_a_hand_calculation(tmp_path: Path) -> None:
    source = ScriptedSource((("2022-03-07", "16:00", {}), ("2022-03-08", "16:00", UP)))
    chosen = settings("itsm", "sizing.amount=1", "params.allow_short=false")
    window = Interval(FIRST, "2022-03-08")
    run = RunJob("itsm", chosen, window, source, tmp_path, ("synthetic",))
    outcome = sequential(tmp_path, [run]).outcomes[0]
    assert outcome.status == "completed", outcome.error
    # 200 shares (all of $20,000 at the 100.00 mid). Base costs: 2 bps of 100.00 each way.
    # Bought 100.02, sold 99.98: gross -8.00. Entry 200 × 0.0035 = 0.70. Exit 0.70 plus
    # 0.0000206 × 19,996.00 = 1.1119, which the engine books as 1.11.
    with ResultStore(tmp_path).connect() as db:
        trade = db.execute(
            "SELECT side, quantity, entry_price, exit_price, gross_pnl, commission, net_pnl,"
            " exit_reason FROM trades"
        ).fetchone()
        fills = db.execute("SELECT side, price, commission FROM fills ORDER BY ts").fetchall()
        orders = db.execute(
            "SELECT kind, side, status FROM orders ORDER BY order_number"
        ).fetchall()
        final = db.execute(
            "SELECT equity, position FROM equity ORDER BY ts DESC LIMIT 1"
        ).fetchone()
    values = [Decimal(x) for x in ("200", "100.02", "99.98", "-8", "1.81", "-9.81")]
    assert trade == ("LONG", *values, "session_flatten")
    assert fills == [
        ("BUY", Decimal("100.02"), Decimal("0.70")),
        ("SELL", Decimal("99.98"), Decimal("1.11")),
    ]
    assert orders == [("entry", "BUY", "filled"), ("exit", "SELL", "filled")]
    assert final == (Decimal("19990.19"), Decimal("0"))


def test_an_interrupted_batch_still_logs_every_attempt(tmp_path: Path) -> None:
    class Interrupted:
        workers = 1

        def run(self, jobs, report) -> None:
            report(0, attempt(jobs[0]))
            raise KeyboardInterrupt

    store = ResultStore(tmp_path)
    jobs = [job(tmp_path, s) for s in ("orb", "trend")]
    with pytest.raises(KeyboardInterrupt):
        run_batch(jobs, Interrupted(), store, label="stopped")
    with store.connect() as db:
        log = db.execute("SELECT strategy, status FROM batches ORDER BY position").fetchall()
        kept = db.execute("SELECT strategy FROM runs").fetchall()
    assert log == [("orb", "completed"), ("trend", "started")] and kept == [("orb",)]


def test_attempts_are_on_record_before_anything_runs(tmp_path: Path) -> None:
    seen: list[tuple[str, str]] = []

    class Observer:
        workers = 1

        def run(self, jobs, report) -> None:
            with ResultStore(tmp_path).connect() as db:
                seen.extend(db.execute("SELECT strategy, status FROM batches").fetchall())
            report(0, attempt(jobs[0]))

    assert run_batch([job(tmp_path, "orb")], Observer(), ResultStore(tmp_path), label="seen").ok
    assert seen == [("orb", "started")]


def test_a_worker_that_ends_between_checks_keeps_its_result(tmp_path: Path) -> None:
    from drift.research import executors

    outcome = attempt(job(tmp_path, "orb"))

    class Pipe:
        written = False

        def poll(self) -> bool:
            return self.written

        def recv(self):
            return outcome

    class Process:
        """Writes its result and exits during the second liveness check."""

        exitcode, calls = 0, 0

        def is_alive(self) -> bool:
            self.calls += 1
            if self.calls == 2:
                pipe.written = True
            return self.calls < 2

        def join(self, timeout: float | None = None) -> None:
            return None

    pipe = Pipe()
    live = executors._Live(job(tmp_path, "orb"), Process(), pipe, 0.0)
    assert [executors._collect(live), executors._collect(live)] == [None, outcome]


def test_default_workers_are_bounded_for_a_laptop() -> None:
    assert default_workers(1) == 1 and 1 <= default_workers(50) <= 4


def test_executor_limits_are_validated() -> None:
    for bad in (dict(workers=0), dict(workers=1, timeout_seconds=0)):
        with pytest.raises(DataError):
            ProcessExecutor(**bad)


def test_a_source_is_picklable_so_a_process_can_rebuild_it() -> None:
    import pickle

    assert pickle.loads(pickle.dumps(SOURCE)) == SOURCE
