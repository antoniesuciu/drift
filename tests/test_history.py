"""Offline monthly Parquet/SQL and development-only baseline checks."""

import json
from dataclasses import replace
from decimal import Decimal

import pytest
from test_alpaca_equity import fixture

from drift.data.alpaca import Credentials
from drift.data.equity import PilotRequest, calendar_from
from drift.data.equity_store import publish
from drift.data.history import (
    StorageLimit,
    baselines,
    check_storage,
    combined,
    connect,
    fetch,
    inspect,
    months,
    partitions,
    role,
)
from drift.data.model import DataError, local_ns


def archive(tmp_path):
    root = tmp_path / "history"
    request = PilotRequest()
    dataset = publish(request, fixture(request), root / "year=2021" / "month=07")
    index = {
        "version": 1,
        "symbol": "NVDA",
        "feed": "sip",
        "adjustment": "raw",
        "months": [
            {
                "month": "2021-07",
                "dataset": str(dataset.relative_to(root)),
                "dataset_id": dataset.name,
                "bars": 1560,
                "missing_minutes": 0,
            }
        ],
    }
    (root / "index.json").write_text(json.dumps(index))
    return root


@pytest.mark.parametrize(
    "start,end",
    [
        ("2019-12", "2020-01"),
        ("2025-12", "2026-01"),
        ("2026-01", "2026-12"),
        ("2021-02", "2021-01"),
        ("2021-00", "2021-02"),
        ("bad", "2021-01"),
    ],
)
def test_rejects_non_development_or_invalid_months(start, end):
    with pytest.raises(DataError):
        months(start, end)


def test_monthly_request_accepts_a_month_and_rejects_longer_bounds():
    assert len(months("2020-01", "2022-12")) == 36
    req = PilotRequest("2020-01-01", "2020-01-31")
    assert req.end == "2020-01-31"
    with pytest.raises(DataError):
        PilotRequest("2020-01-01", "2020-02-01")
    with pytest.raises(DataError):
        PilotRequest("2026-01-01", "2026-01-31")
    receipt = fixture()[0]
    rows = json.loads(receipt.body)
    # Same data contract accepts a calendar longer than the original ten-session pilot.
    days = [f"2020-01-{i:02d}" for i in range(1, 24)]
    receipt = replace(receipt, body=json.dumps([{**rows[0], "date": d} for d in days]).encode())
    assert len(calendar_from(req, receipt).sessions) == 23


def test_duckdb_direct_parquet_values_precision_and_source(tmp_path):
    root = archive(tmp_path)
    report = inspect(root)
    assert report["bars"] == 1560 and report["duplicates"] == report["invalid_rows"] == 0
    with connect(root) as db:
        value = db.execute(
            "SELECT open, feed, available_ns-end_ns FROM bars ORDER BY start_ns LIMIT 1"
        ).fetchone()
        assert value == (Decimal("800.0001"), "sip", 1_000_000_000)
    data, splits = combined(root)
    assert len(data.candles) == 1560 and data.source_feed == "sip"
    assert splits[0]["day"] == "2021-07-20" and splits[0]["ratio"] == "4"


def test_index_cannot_escape_root_or_claim_other_feed_or_identity(tmp_path):
    root = archive(tmp_path)
    path = root / "index.json"
    initial = json.loads(path.read_text())
    for field, value in (("dataset", "../outside"), ("dataset_id", "0" * 64)):
        index = json.loads(json.dumps(initial))
        index["months"][0][field] = value
        path.write_text(json.dumps(index))
        with pytest.raises((DataError, OSError)):
            partitions(root)


def test_analytical_parquet_corruption_is_detected(tmp_path):
    root = archive(tmp_path)
    target = partitions(root)[0] / "bars.parquet"
    target.write_bytes(b"corrupt")
    with pytest.raises(DataError):
        inspect(root)


def test_all_six_baselines_keep_raw_units_costs_and_reproduce(tmp_path):
    root = archive(tmp_path)
    first = baselines(root, tmp_path / "results")
    assert set(first["reports"]) == {
        "itsm",
        "orb",
        "vwap_reversion",
        "bollinger_reversion",
        "reversal",
        "trend",
    }
    protocol = json.loads(
        (next((tmp_path / "results").glob("baseline-*")) / "protocol.json").read_text()
    )
    assert all(c["costs"]["slippage_ticks"] == 1 for c in protocol["configs"].values())
    assert all(
        c["strategy"]["params"]["allow_short"] is False for c in protocol["configs"].values()
    )
    second = baselines(root, tmp_path / "results")
    assert first["reports"] == second["reports"]


def test_storage_cap_stops_before_any_download_and_preserves_index(tmp_path):
    root = tmp_path / "limited"
    result = fetch(
        root,
        Credentials("synthetic-key", "synthetic-secret"),
        "2020-01",
        "2020-01",
        max_bytes=1,
        min_free_bytes=0,
    )
    assert result["stop_reason"] == "storage_budget"
    assert result["months"] == [] and not list(root.rglob("*.parquet"))
    with pytest.raises(StorageLimit):
        check_storage(root, 1024**3, 10**30)


def test_later_years_can_be_archived_but_are_not_enabled_for_backtesting(tmp_path):
    from drift.backtest.config import BacktestConfig, default_config
    from drift.backtest.data import MarketData
    from drift.backtest.engine import run_on
    from drift.strategies.calendar import Calendar, SessionSpec

    assert len(months("2020-01", "2025-12")) == 72
    assert role("2022-12") == "development"
    assert role("2023-01") == "validation" and role("2025-12") == "holdout"
    request = PilotRequest("2024-06-01", "2024-06-30")
    assert request.end == "2024-06-30"
    root = archive(tmp_path)
    data, _ = combined(root)
    first = data.candles[0]
    day = "2024-06-10"
    shift = local_ns(day, "09:30") - first.start
    candle = replace(
        first,
        start=first.start + shift,
        end=first.end + shift,
        available=first.available + shift,
        day=day,
    )
    heldout = MarketData.build(
        data.instrument,
        Calendar((SessionSpec(day),)),
        (candle,),
        source_ref=data.source_ref,
        source_feed="sip",
    )
    raw = default_config("itsm")
    raw.update(
        version=2,
        synthetic=False,
        instrument={**raw["instrument"], "symbol": "NVDA", "data_precision": 4},
        data={"dataset_id": data.source_ref},
    )
    with pytest.raises(DataError, match="validation/holdout"):
        run_on(BacktestConfig.parse(raw), heldout)


def test_six_decimal_source_price_survives_native_and_mixed_sql_schemas(tmp_path, monkeypatch):
    import drift.data.history as history
    from drift.data.alpaca import decode
    from drift.data.equity_store import load

    request = PilotRequest()
    records = fixture(request)
    ordinary = publish(request, records, tmp_path / "ordinary")
    body = decode(records[2].body)
    body["bars"]["NVDA"][0]["h"] = "800.123456"
    records[2] = replace(records[2], body=json.dumps(body, default=str).encode())
    precise = publish(request, records, tmp_path / "precise")
    data, manifest = load(precise)
    assert data.instrument.precision == manifest["instrument"]["data_precision"] == 6
    assert data.instrument.tick == Decimal("0.01")
    assert data.candles[0].high == Decimal("800.123456")
    # Test the SQL reader's common decimal type rather than silently casting to file one's scale.
    monkeypatch.setattr(history, "partitions", lambda *a, **kw: [ordinary, precise])
    with connect(tmp_path) as db:
        assert db.execute("SELECT max(high) FROM bars").fetchone()[0] == Decimal("800.123456")
