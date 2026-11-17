from datetime import timedelta
from importlib import import_module

import pytest

from drift.smoke import SmokeConfig, run_smoke


def test_real_engine_replay_is_deterministic_and_order_free() -> None:
    first = run_smoke()
    assert first == run_smoke()
    assert first.synthetic is True
    assert first.framework_version == "1.231.0"
    assert first.instrument_id == "MESZ6.CME"
    assert first.tick_value_usd == "1.25"
    assert first.closes == ("5000.25", "5000.50", "5000.75")
    assert first.iterations == 3
    assert first.total_orders == first.total_positions == 0
    assert first.event_times_ns == (
        1773063060000000000,
        1773063120000000000,
        1773063180000000000,
    )
    assert first.observed_times_ns == tuple(t + 100_000_000 for t in first.event_times_ns)


@pytest.mark.parametrize("count", [1, 10])
def test_configured_fixture_size_is_actually_replayed(count: int) -> None:
    result = run_smoke(SmokeConfig(bar_count=count, delivery_delay=timedelta(seconds=2)))
    assert len(result.closes) == result.iterations == count
    assert all(
        observed - event == 2_000_000_000
        for event, observed in zip(result.event_times_ns, result.observed_times_ns, strict=True)
    )
    assert result.total_orders == 0


@pytest.mark.parametrize("value", [0, -1, 11, True, 1.5, "3"])
def test_invalid_fixture_size(value: object) -> None:
    with pytest.raises(ValueError, match="bar_count"):
        SmokeConfig(bar_count=value)  # type: ignore[arg-type]


@pytest.mark.parametrize("value", [timedelta(microseconds=-1), timedelta(minutes=1), 0, None])
def test_invalid_delivery_delay(value: object) -> None:
    with pytest.raises(ValueError, match="delivery_delay"):
        SmokeConfig(delivery_delay=value)  # type: ignore[arg-type]


def test_zero_latency_still_delivers_only_completed_bars() -> None:
    result = run_smoke(SmokeConfig(delivery_delay=timedelta(0)))
    assert result.observed_times_ns == result.event_times_ns


def test_invalid_configuration_type() -> None:
    with pytest.raises(ValueError, match="SmokeConfig"):
        run_smoke({"mode": "live"})  # type: ignore[arg-type]


def test_ib_adapter_imports_without_creating_clients_or_connecting() -> None:
    # Imports only. Socket access is blocked for every test by pytest-socket.
    config = import_module("nautilus_trader.adapters.interactive_brokers.config")
    data = import_module("nautilus_trader.adapters.interactive_brokers.data")
    execution = import_module("nautilus_trader.adapters.interactive_brokers.execution")
    factories = import_module("nautilus_trader.adapters.interactive_brokers.factories")
    assert config.InteractiveBrokersDataClientConfig
    assert data.InteractiveBrokersDataClient
    assert execution.InteractiveBrokersExecutionClient
    assert factories.InteractiveBrokersLiveDataClientFactory
