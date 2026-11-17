"""`drift research` and `drift portfolio`, end to end on synthetic data."""

import json
import sys
from pathlib import Path

import pytest

from drift.__main__ import main
from drift.backtest import registry
from drift.backtest.config import STRATEGIES
from drift.research.cli import main as cli
from drift.research.store import ResultStore

RANGE = ("--start", "2022-03-07", "--end", "2022-03-11")
SYNTHETIC = ("--source", "synthetic")


def research(capsys, store: Path, *args: str) -> tuple[int, str]:
    code = cli(["research", "run", "--store", str(store), *SYNTHETIC, *args])
    return code, capsys.readouterr().out


def portfolio(capsys, store: Path, command: str, *args: str) -> tuple[int, str]:
    code = cli(["portfolio", command, "--store", str(store), *args])
    return code, capsys.readouterr().out


def test_module_entry_point_reaches_the_research_commands(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["drift", "research", "strategies"])
    with pytest.raises(SystemExit) as error:
        main()
    out = capsys.readouterr().out
    assert error.value.code == 0 and "itsm" in out and "RULE" in out


def test_run_selected_strategies_concurrently_and_compare(tmp_path: Path, capsys) -> None:
    store = tmp_path / "store"
    code, out = research(capsys, store, *RANGE, "--strategies", "orb,trend", "--workers", "2")
    assert code == 0 and "Synthetic data" in out and "orb" in out and "trend" in out
    assert cli(["research", "compare", "--store", str(store), "--json"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert {r["strategy"] for r in rows} == {"orb", "trend"}
    assert cli(["research", "show", rows[0]["run_id"], "--store", str(store)]) == 0
    assert json.loads(capsys.readouterr().out)["run_id"] == rows[0]["run_id"]


def test_run_all_strategies_is_the_default(tmp_path: Path, capsys, monkeypatch) -> None:
    builtin = {name: registry.strategy_entry(name) for name in STRATEGIES}
    monkeypatch.setattr(registry, "_REGISTRY", builtin)  # other tests register crashing plugins
    code, _ = research(capsys, tmp_path, *RANGE, "--sequential")
    assert code == 0
    with ResultStore(tmp_path).connect() as db:
        assert db.execute("SELECT count(*) FROM runs").fetchone() == (len(STRATEGIES),)


def test_costs_capital_and_parameters_are_configurable(tmp_path: Path, capsys) -> None:
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"orb": {"params": {"horizon_seconds": 900}}}))
    code, _ = research(
        capsys,
        tmp_path / "store",
        *RANGE,
        "--strategies",
        "orb",
        "--sequential",
        "--capital",
        "50000",
        "--costs",
        "stressed",
        "--set",
        "execution.slippage_bps=7",
        "--settings",
        str(settings),
    )
    assert code == 0
    with ResultStore(tmp_path / "store").connect() as db:
        capital, profile, raw = db.execute(
            "SELECT capital, cost_profile, config_json FROM runs"
        ).fetchone()
    config = json.loads(raw)
    assert (int(capital), profile) == (50000, "custom")
    assert config["costs"]["slippage_bps"] == "7"
    assert config["strategy"]["params"]["horizon_seconds"] == 900


def test_a_failure_is_reported_and_the_rest_still_run(tmp_path: Path, capsys) -> None:
    code, out = research(
        capsys,
        tmp_path,
        *RANGE,
        "--plugin",
        "research_plugin",
        "--strategies",
        "broken,orb",
        "--workers",
        "2",
    )
    assert code == 1 and "FAILED broken: RuntimeError" in out and "orb" in out


def test_a_bad_sort_column_is_refused_before_any_simulation(tmp_path: Path, capsys) -> None:
    code, out = research(capsys, tmp_path, *RANGE, "--strategies", "orb", "--sort", "nope")
    assert code == 2 and "unknown column" in out
    with ResultStore(tmp_path).connect() as db:
        assert db.execute("SELECT count(*) FROM batches").fetchone() == (0,)


def test_settings_files_follow_the_same_decimal_rule_as_overrides(tmp_path: Path, capsys) -> None:
    settings = tmp_path / "settings.json"
    settings.write_text('{"sizing": {"amount": 0.5}}')
    args = (*RANGE, "--strategies", "orb", "--sequential", "--settings", str(settings))
    assert research(capsys, tmp_path / "store", *args)[0] == 0
    settings.write_text("[1, 2]")
    code, out = research(capsys, tmp_path / "store", *args)
    assert code == 2 and "object" in out


def test_invalid_settings_stop_before_any_strategy_runs(tmp_path: Path, capsys) -> None:
    code, out = research(capsys, tmp_path, *RANGE, "--set", "risk.max_notional=0")
    assert code == 2 and "risk limit" in out
    with ResultStore(tmp_path).connect() as db:
        assert db.execute("SELECT count(*) FROM batches").fetchone() == (0,)


def test_an_override_can_replace_a_null_setting(tmp_path: Path, capsys) -> None:
    store = tmp_path / "store"
    portfolio(capsys, store, "create", "alpha", "--strategy", "orb")
    assert portfolio(capsys, store, "configure", "alpha", "--set", "exit.stop=null")[0] == 0
    code, out = portfolio(capsys, store, "configure", "alpha", "--set", "exit.stop.kind=ticks")
    assert code == 2 and out.startswith("drift:")
    code, out = portfolio(
        capsys,
        store,
        "configure",
        "alpha",
        "--set",
        "exit.stop.kind=ticks",
        "--set",
        "exit.stop.value=50",
    )
    assert code == 0 and "version 3" in out


def test_the_research_split_is_enforced_before_any_data_is_read(tmp_path: Path, capsys) -> None:
    missing = tmp_path / "no-archive"
    for period, reason in (("2024", "holdout"), ("2023", "allow-validation")):
        code = cli(
            [
                "research",
                "run",
                "--year",
                period,
                "--archive",
                str(missing),
                "--store",
                str(tmp_path / "store"),
                "--allow-validation" if period == "2024" else "--sequential",
            ]
        )
        assert code == 2 and reason in capsys.readouterr().out


@pytest.mark.parametrize(
    "args",
    [
        ("--year", "2022", "--start", "2022-01-01"),
        ("--start", "2022-01-01"),
        (*RANGE, "--strategies", "nonsense"),
        (*RANGE, "--sequential", "--workers", "2"),
        (*RANGE, "--workers", "0"),
        (*RANGE, "--set", "nonsense=1"),
        (*RANGE, "--capital", "abc"),
        (*RANGE, "--sort", "nonsense"),
    ],
)
def test_usage_errors_exit_cleanly(tmp_path: Path, capsys, args) -> None:
    code, out = research(capsys, tmp_path, *args)
    assert code == 2 and out.startswith(("drift:", "Synthetic"))


def test_portfolio_lifecycle(tmp_path: Path, capsys) -> None:
    store = tmp_path / "store"
    code, out = portfolio(capsys, store, "create", "alpha", "--strategy", "reversal")
    assert code == 0 and "20000" in out
    assert (
        portfolio(capsys, store, "create", "beta", "--strategy", "orb", "--capital", "30000")[0]
        == 0
    )
    first = ("--start", "2022-03-07", "--end", "2022-03-11", *SYNTHETIC, "--sequential")
    assert portfolio(capsys, store, "advance", "alpha", "beta", *first)[0] == 0
    code, out = portfolio(
        capsys, store, "configure", "alpha", "--set", "params.horizon_seconds=600"
    )
    assert code == 0 and "version 2" in out
    code, out = portfolio(capsys, store, "advance", "alpha", "--end", "2022-03-18", *SYNTHETIC)
    assert code == 0 and "2022-03-18" in out
    code, out = portfolio(capsys, store, "list")
    assert code == 0 and "alpha" in out and "beta" in out and "30000" in out
    code, out = portfolio(capsys, store, "show", "alpha")
    report = json.loads(out)
    assert code == 0 and report["through"] == "2022-03-18" and len(report["segments"]) == 2
    assert [v["version"] for v in report["config_versions"]] == [1, 2]
    assert report["metrics"]["trades"] > 0


def test_portfolio_errors_exit_cleanly(tmp_path: Path, capsys) -> None:
    store = tmp_path / "store"
    assert portfolio(capsys, store, "list")[1].strip() == "no portfolios"
    assert portfolio(capsys, store, "show", "absent")[0] == 2
    portfolio(capsys, store, "create", "alpha", "--strategy", "orb")
    assert portfolio(capsys, store, "advance", "alpha", *SYNTHETIC)[0] == 2
    assert portfolio(capsys, store, "advance", "alpha", "--end", "2022-03-18", *SYNTHETIC)[0] == 2
    code, out = portfolio(capsys, store, "create", "alpha", "--strategy", "orb")
    assert code == 2 and "already exists" in out
