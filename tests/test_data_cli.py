import json
import sys
from pathlib import Path

import pytest

from quantlab.__main__ import main
from quantlab.data.model import DataError
from quantlab.data.store import load_dataset, publication_lock


def test_demo_and_replay_cli_are_offline_and_deterministic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    for _ in range(2):
        monkeypatch.setattr(
            sys, "argv", ["quantlab", "data-demo", "--output", str(tmp_path / "data")]
        )
        main()
        report = json.loads(capsys.readouterr().out)
        assert report["orders"] == report["positions"] == 0
        assert report["bars"] == 2160
        if _ == 0:
            first = report
        else:
            assert report == first
    monkeypatch.setattr(
        sys, "argv", ["quantlab", "data-replay", "--dataset", first["dataset_path"]]
    )
    main()
    assert (
        json.loads(capsys.readouterr().out)["observations_sha256"] == first["observations_sha256"]
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "quantlab",
            "data-ingest",
            "--request",
            str(tmp_path / "data" / "synthetic-input" / "request.json"),
            "--output",
            str(tmp_path / "data"),
        ],
    )
    main()
    assert json.loads(capsys.readouterr().out)["dataset_version"] == first["dataset_version"]


@pytest.mark.parametrize(
    "args",
    [
        ["data-ingest"],
        ["data-demo"],
        ["data-replay"],
        ["data-replay", "--dataset", "x", "--output", "y"],
        ["smoke", "--request", "x"],
        ["data-demo", "--output", "x", "--request", "y"],
    ],
)
def test_cli_rejects_missing_or_wrong_arguments(args, monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["quantlab", *args])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2
    capsys.readouterr()


def test_crash_lock_is_not_automatically_stolen(tmp_path: Path) -> None:
    with publication_lock(tmp_path, "a" * 64):
        with pytest.raises(DataError, match="locked"):
            with publication_lock(tmp_path, "a" * 64):
                pytest.fail("second publisher must not run")
    assert not list(tmp_path.glob("*.lock"))


def test_arbitrary_catalog_path_cannot_be_replayed(tmp_path: Path) -> None:
    with pytest.raises(DataError, match="published"):
        load_dataset(tmp_path)
