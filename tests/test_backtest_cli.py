"""`drift backtest`: choose a strategy, configure it, run it offline, inspect, reproduce."""

import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from helpers import merge

from drift.__main__ import MAX_CONFIG_BYTES, main
from drift.backtest import engine
from drift.backtest.config import STRATEGIES, BacktestConfig, default_config

BROKEN_RECONCILIATION = {
    "engine_balance": "1",
    "ledger_balance": "2",
    "difference": "-1",
    "tolerance": "0",
    "ok": False,
}


def run_cli(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], *args: str) -> str:
    monkeypatch.setattr(sys, "argv", ["drift", "backtest", *args])
    main()
    return capsys.readouterr().out


def fail(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], *args: str) -> str:
    monkeypatch.setattr(sys, "argv", ["drift", *args])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    return capsys.readouterr().err


def write_config(tmp_path: Path, strategy: str, **patch: object) -> Path:
    path = tmp_path / f"{strategy}.json"
    path.write_text(json.dumps(merge(default_config(strategy), {"data": {"sessions": 4}} | patch)))
    return path


@pytest.mark.parametrize("strategy", ["itsm", "trend"])
def test_builtin_strategy_runs_and_reports_json_and_text(
    strategy: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    report = json.loads(run_cli(monkeypatch, capsys, "--strategy", strategy, "--json"))
    assert report["synthetic"] is True and report["config"]["strategy"]["name"] == strategy
    assert report["reconciliation"]["ok"] is True and report["engine"]["iterations"] > 0
    text = run_cli(monkeypatch, capsys, "--strategy", strategy)
    assert text.startswith(f"# Backtest report: {strategy}-synthetic-demo")
    assert report["results_sha256"][:16] in text


def test_results_reproduce_across_invocations_and_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config = write_config(tmp_path, "trend")
    args = ("--config", str(config), "--json")
    first = json.loads(run_cli(monkeypatch, capsys, *args, "--output", str(tmp_path / "one")))
    second = json.loads(run_cli(monkeypatch, capsys, *args, "--output", str(tmp_path / "two")))
    assert first == second and first["metrics"]["trades"] > 0
    for name in ("report.json", "report.md", "trades.csv"):
        assert (tmp_path / "one" / name).read_bytes() == (tmp_path / "two" / name).read_bytes()
    saved = json.loads((tmp_path / "one" / "report.json").read_text())
    assert saved["results_sha256"] == first["results_sha256"]
    assert (
        len((tmp_path / "one" / "trades.csv").read_text().splitlines())
        == first["metrics"]["trades"] + 1
    )


def test_dumped_configuration_is_editable_and_changes_the_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    dumped = json.loads(run_cli(monkeypatch, capsys, "--strategy", "itsm", "--dump-config"))
    assert BacktestConfig.parse(dumped).strategy.name == "itsm"
    dumped["data"]["sessions"] = 4
    path = tmp_path / "cfg.json"
    path.write_text(json.dumps(dumped))
    base = json.loads(run_cli(monkeypatch, capsys, "--config", str(path), "--json"))
    dumped["strategy"]["params"] = {"allow_short": False}
    path.write_text(json.dumps(dumped))
    changed = json.loads(run_cli(monkeypatch, capsys, "--config", str(path), "--json"))
    assert changed["config_sha256"] != base["config_sha256"]
    assert changed["metrics"]["short_trades"] == 0
    assert changed["data_sha256"] == base["data_sha256"]  # same market, different strategy settings


def test_usage_and_configuration_errors_exit_cleanly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert "exactly one of --config or --strategy" in fail(monkeypatch, capsys, "backtest")
    both = ("backtest", "--config", "x.json", "--strategy", "itsm")
    assert "exactly one" in fail(monkeypatch, capsys, *both)
    assert "only combines with --strategy" in fail(
        monkeypatch, capsys, "backtest", "--strategy", "itsm", "--dump-config", "--output", "o"
    )
    assert "apply to backtest only" in fail(monkeypatch, capsys, "smoke", "--strategy", "itsm")
    assert "backtest takes" in fail(
        monkeypatch, capsys, "backtest", "--strategy", "itsm", "--dataset", "d"
    )
    missing = fail(monkeypatch, capsys, "backtest", "--config", str(tmp_path / "none.json"))
    assert "local file operation failed" in missing
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(merge(default_config("itsm"), {"risk": {"max_notional": "0"}})))
    assert "drift: every risk limit" in fail(monkeypatch, capsys, "backtest", "--config", str(bad))
    bad.write_text("{not json")
    assert fail(monkeypatch, capsys, "backtest", "--config", str(bad)).startswith("drift:")
    live = merge(default_config("itsm"), {})
    live["synthetic"] = False
    bad.write_text(json.dumps(live))
    assert "synthetic" in fail(monkeypatch, capsys, "backtest", "--config", str(bad))
    bad.write_text(json.dumps(merge(default_config("itsm"), {"sizing": {"amount": "1E+30"}})))
    assert fail(monkeypatch, capsys, "backtest", "--config", str(bad)).startswith("drift:")
    bad.write_text("[" * 200_000)
    assert fail(monkeypatch, capsys, "backtest", "--config", str(bad)).startswith("drift:")
    bad.write_text(" " * (MAX_CONFIG_BYTES + 1))
    assert "too large" in fail(monkeypatch, capsys, "backtest", "--config", str(bad))


def test_report_refuses_to_write_through_a_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    victim, out = tmp_path / "victim.txt", tmp_path / "out"
    victim.write_text("keep")
    out.mkdir()
    (out / "report.md").symlink_to(victim)
    config = write_config(tmp_path, "itsm")
    args = ("backtest", "--config", str(config), "--output", str(out))
    assert "symlink" in fail(monkeypatch, capsys, *args)
    assert victim.read_text() == "keep" and not (out / "report.json").exists()


def test_reconciliation_mismatch_fails_the_run_after_reporting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    real = engine.run_backtest
    monkeypatch.setattr(
        engine,
        "run_backtest",
        lambda config: replace(real(config), reconciliation=BROKEN_RECONCILIATION),
    )
    config = write_config(tmp_path, "itsm")
    monkeypatch.setattr(sys, "argv", ["drift", "backtest", "--config", str(config)])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    captured = capsys.readouterr()
    assert "MISMATCH" in captured.out and "do not reconcile" in captured.err


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_every_strategy_runs_from_a_config_file_and_reproduces(
    strategy: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = write_config(tmp_path, strategy)
    first = json.loads(run_cli(monkeypatch, capsys, "--config", str(config), "--json"))
    second = json.loads(run_cli(monkeypatch, capsys, "--config", str(config), "--json"))
    assert first == second and first["config"]["strategy"]["name"] == strategy
    assert first["reconciliation"]["ok"] is True and first["synthetic"] is True


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_dumped_demo_configuration_parses_for_every_strategy(
    strategy: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    dumped = json.loads(run_cli(monkeypatch, capsys, "--strategy", strategy, "--dump-config"))
    assert BacktestConfig.parse(dumped).strategy.name == strategy
