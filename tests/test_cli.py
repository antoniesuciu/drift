import json
import socket
import sys
from importlib.metadata import version

import pytest
from pytest_socket import SocketBlockedError

import drift
from drift.__main__ import main


def test_installable_package_version() -> None:
    assert drift.__version__ == version("drift") == "0.1.0"


def test_cli_runs_synthetic_engine(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setattr(sys, "argv", ["drift", "smoke"])
    main()
    report = json.loads(capsys.readouterr().out)
    assert report["synthetic"] is True
    assert report["iterations"] == 3
    assert report["total_orders"] == report["total_positions"] == 0


@pytest.mark.parametrize("command", ["live", "paper", "connect", "download"])
def test_cli_rejects_network_and_order_modes(
    command: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setattr(sys, "argv", ["drift", command])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


def test_network_is_disabled_for_the_test_suite() -> None:
    with pytest.warns(UserWarning, match="socket.socket"), pytest.raises(SocketBlockedError):
        socket.socket()
