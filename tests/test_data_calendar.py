"""Synthetic calendar/contract scenarios; no claimed vendor calendar coverage."""

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from quantlab.data.core import coverage, normalize, snapshot
from quantlab.data.databento import decode
from quantlab.data.model import (
    MINUTE,
    SECOND,
    Config,
    Contract,
    DataError,
    digest,
    instant,
    local_ns,
)
from quantlab.data.replay import replay_dataset
from quantlab.data.store import ingest, load_dataset
from quantlab.data.synthetic import write_dbn, write_demo


def march_fixture(tmp_path: Path) -> Path:
    request = write_demo(tmp_path / "march")
    config = json.loads(request.read_text())
    contract = config["contracts"][0]
    old = dict(contract, month="202203", raw_symbol="MESH2", expiration="2022-03-18T13:30:00Z")
    new = dict(
        contract,
        month="202206",
        raw_symbol="MESM2",
        provider_id=456,
        expiration="2022-06-17T13:30:00Z",
    )
    config.update(
        contracts=[old, new],
        start="2022-03-09T00:00:00Z",
        end="2022-03-17T00:00:00Z",
        study_start="2022-03-11",
        study_end="2022-03-16",
        calendar_version="synthetic-march2022-v1",
        rolls=[{"day": "2022-03-14", "outgoing": "202203", "incoming": "202206"}],
    )
    sessions = []
    records = []
    for i in range(7):
        d = date(2022, 3, 10) + timedelta(days=i)
        day = d.isoformat()
        full = d.weekday() < 5
        sessions.append(
            {
                "day": day,
                "cash_close": "16:00" if full else None,
                "cme_intervals": [
                    [
                        instant(local_ns((d - timedelta(days=1)).isoformat(), "18:00")).isoformat(),
                        instant(local_ns(day, "17:00")).isoformat(),
                    ]
                ]
                if full
                else [],
            }
        )
        if full:
            for c in [old, new]:
                for start in range(local_ns(day, "09:30"), local_ns(day, "16:00"), MINUTE):
                    base = 4000 if c == old else 5000
                    records.append(
                        (
                            c["provider_id"],
                            start,
                            base * 10**9,
                            (base + 1) * 10**9,
                            (base - 1) * 10**9,
                            base * 10**9,
                            10,
                        )
                    )
    config["sessions"] = sessions
    write_dbn(request.parent / "definitions.dbn.zst", config["contracts"], [], definitions=True)
    write_dbn(request.parent / "bars.dbn.zst", config["contracts"], records)
    config["chunks"][0].update(
        start=config["start"],
        end=config["end"],
        sha256=digest((request.parent / "bars.dbn.zst").read_bytes()),
        definitions_sha256=digest((request.parent / "definitions.dbn.zst").read_bytes()),
    )
    request.write_text(json.dumps(config))
    return request


def test_native_march_roll_dst_and_contract_identity(tmp_path: Path) -> None:
    request = march_fixture(tmp_path)
    path = ingest(request, tmp_path / "data")
    dataset = load_dataset(path)
    friday = dataset.snapshot("2022-03-11", local_ns("2022-03-11", "15:30") + SECOND)
    monday = dataset.snapshot("2022-03-14", local_ns("2022-03-14", "15:30") + SECOND)
    tuesday = dataset.snapshot("2022-03-15", local_ns("2022-03-15", "15:30") + SECOND)
    assert friday["inputs_ready"] and friday["contract"] == "CME:MES:202203"
    assert friday["values"]["10:00"]["end"] == 1647010800000000000  # 15:00 UTC
    assert monday["values"]["10:00"]["end"] == 1647266400000000000  # 14:00 UTC
    assert "roll_session" in monday["reasons"]
    assert not monday["inputs_ready"]  # New contract's Friday price cannot evade the exclusion.
    assert tuesday["inputs_ready"] and tuesday["contract"] == "CME:MES:202206"
    assert tuesday["values"]["previous_close"]["contract"] == "CME:MES:202206"
    assert all(p["close"] == "5000.00" for p in tuesday["values"].values())
    assert replay_dataset(path)["bars"] == 3900


def test_previous_friday_close_uses_its_own_dst_offset(tmp_path: Path) -> None:
    request = march_fixture(tmp_path)
    value = json.loads(request.read_text())
    value["contracts"] = value["contracts"][:1]
    value["rolls"] = []
    config = Config.parse(value)
    # Direct provider-independent rows from a valid two-contract decode, keep March only.
    original = Config.parse(json.loads(request.read_text()))
    records, _, _ = decode(original, request.parent)
    rows, _ = normalize(original, records)
    result = snapshot(
        config,
        [r for r in rows if r.contract == "CME:MES:202203"],
        "2022-03-14",
        local_ns("2022-03-14", "15:30") + SECOND,
    )
    assert result["inputs_ready"]
    assert result["values"]["previous_close"]["end"] == 1647032400000000000  # Friday21:00UTC
    assert result["values"]["15:30"]["end"] == 1647286200000000000  # Monday19:30UTC


def test_fall_dst_keeps_cash_endpoints_and_previous_close_in_local_time(tmp_path: Path) -> None:
    request = write_demo(tmp_path / "fall")
    value = json.loads(request.read_text())
    value.update(
        start="2022-11-02T00:00:00Z",
        end="2022-11-10T00:00:00Z",
        study_start="2022-11-04",
        study_end="2022-11-09",
        calendar_version="synthetic-fall-dst2022-v1",
    )
    sessions = []
    records = []
    for i in range(7):
        day = date(2022, 11, 3) + timedelta(days=i)
        label = day.isoformat()
        full = day.weekday() < 5
        sessions.append(
            {
                "day": label,
                "cash_close": "16:00" if full else None,
                "cme_intervals": [
                    [
                        instant(
                            local_ns((day - timedelta(days=1)).isoformat(), "18:00")
                        ).isoformat(),
                        instant(local_ns(label, "17:00")).isoformat(),
                    ]
                ]
                if full
                else [],
            }
        )
        if full:
            records.extend(
                (123, start, 5000 * 10**9, 5001 * 10**9, 4999 * 10**9, 5000 * 10**9, 10)
                for start in range(local_ns(label, "09:30"), local_ns(label, "16:00"), MINUTE)
            )
    value["sessions"] = sessions
    write_dbn(request.parent / "bars.dbn.zst", value["contracts"], records)
    value["chunks"][0].update(
        start=value["start"],
        end=value["end"],
        sha256=digest((request.parent / "bars.dbn.zst").read_bytes()),
    )
    request.write_text(json.dumps(value))
    path = ingest(request, tmp_path / "data")
    dataset = load_dataset(path)
    friday = dataset.snapshot("2022-11-04", local_ns("2022-11-04", "15:30") + SECOND)
    monday = dataset.snapshot("2022-11-07", local_ns("2022-11-07", "15:30") + SECOND)
    assert friday["inputs_ready"] and monday["inputs_ready"]
    assert instant(friday["values"]["10:00"]["end"]).isoformat() == "2022-11-04T14:00:00+00:00"
    assert instant(monday["values"]["10:00"]["end"]).isoformat() == "2022-11-07T15:00:00+00:00"
    assert (
        instant(monday["values"]["previous_close"]["end"]).isoformat()
        == "2022-11-04T20:00:00+00:00"
    )
    assert (
        instant(monday["values"]["15:30"]["available"]).isoformat() == "2022-11-07T20:30:01+00:00"
    )
    assert replay_dataset(path)["bars"] == 1950


@pytest.mark.parametrize("day", ["2022-03-10", "2022-03-15"])
def test_wrong_roll_schedule_is_rejected(tmp_path: Path, day: str) -> None:
    value = json.loads(march_fixture(tmp_path).read_text())
    value["rolls"][0]["day"] = day
    with pytest.raises(DataError, match="fixed Monday"):
        Config.parse(value)


def test_year_end_roll_and_holiday_adjustment(tmp_path: Path) -> None:
    value = json.loads(write_demo(tmp_path / "input").read_text())
    old = value["contracts"][0]
    new = dict(
        old, month="202303", raw_symbol="MESH3", provider_id=456, expiration="2023-03-17T13:30:00Z"
    )
    value.update(
        contracts=[old, new],
        start="2022-12-08T00:00:00Z",
        end="2022-12-16T00:00:00Z",
        study_start="2022-12-12",
        study_end="2022-12-15",
        rolls=[{"day": "2022-12-13", "outgoing": "202212", "incoming": "202303"}],
    )
    value["sessions"] = []
    for i in range(7):
        d = date(2022, 12, 9) + timedelta(days=i)
        # Synthetic exceptional Monday closure: next full cash day is Tuesday.
        value["sessions"].append(
            {
                "day": d.isoformat(),
                "cash_close": "16:00" if d.weekday() < 5 and d.day != 12 else None,
                "cme_intervals": [],
            }
        )
    value["chunks"][0].update(start=value["start"], end=value["end"])
    config = Config.parse(value)
    assert config.selected("2022-12-09").month == "202212"
    assert config.selected("2022-12-13").month == "202303"
    assert (
        "roll_session"
        in snapshot(config, [], "2022-12-13", local_ns("2022-12-13", "15:30") + SECOND)["reasons"]
    )


def test_expiration_exception_is_explicit_not_assumed_friday(tmp_path: Path) -> None:
    c = json.loads(write_demo(tmp_path / "input").read_text())["contracts"][0]
    exception = dict(c, month="202606", raw_symbol="MESM6", expiration="2026-06-18T13:30:00Z")
    assert instant(Contract.parse(exception).expiration).weekday() == 3


def test_bars_at_or_after_expiration_are_rejected(tmp_path: Path) -> None:
    request = write_demo(tmp_path / "input")
    value = json.loads(request.read_text())
    value["end"] = "2023-01-01T00:00:00Z"
    value["chunks"][0]["end"] = value["end"]
    start = Contract.parse(value["contracts"][0]).expiration
    write_dbn(
        request.parent / "bars.dbn.zst",
        value["contracts"],
        [(123, start, 5000 * 10**9, 5001 * 10**9, 4999 * 10**9, 5000 * 10**9, 10)],
    )
    value["chunks"][0]["sha256"] = digest((request.parent / "bars.dbn.zst").read_bytes())
    request.write_text(json.dumps(value))
    with pytest.raises(DataError, match="lifetime"):
        ingest(request, tmp_path / "data")


def test_scheduled_exchange_pause_is_not_unknown_gap(tmp_path: Path) -> None:
    request = write_demo(tmp_path / "input")
    value = json.loads(request.read_text())
    config = Config.parse(value)
    records, _, _ = decode(config, request.parent)
    rows, _ = normalize(config, records)
    pause = local_ns("2022-11-22", "12:00")
    rows = [r for r in rows if r.start != pause]
    day = next(s for s in value["sessions"] if s["day"] == "2022-11-22")
    first, end = day["cme_intervals"][0]
    day["cme_intervals"] = [
        [first, instant(pause).isoformat()],
        [instant(pause + MINUTE).isoformat(), end],
        day["cme_intervals"][1],
    ]
    changed = Config.parse(value)
    result = next(c for c in coverage(changed, rows) if c["day"] == day["day"])
    assert result["scheduled_closed_minutes"] == 1
    assert result["unknown_gap_count"] == 0
    assert result["inputs_ready"]


def test_cme_bar_can_exist_on_cash_holiday(tmp_path: Path) -> None:
    request = write_demo(tmp_path / "input")
    config = Config.parse(json.loads(request.read_text()))
    start = local_ns("2022-11-24", "10:00")
    assert config.session_for(start, start + MINUTE).day == "2022-11-24"
    assert "cash_closed" in snapshot(config, [], "2022-11-24", start)["reasons"]


def test_empty_chunk_is_accounted_for_without_fabricating_bars(tmp_path: Path) -> None:
    request = write_demo(tmp_path / "input")
    value = json.loads(request.read_text())
    write_dbn(request.parent / "empty.dbn.zst", value["contracts"], [])
    empty = dict(
        value["chunks"][0],
        path="empty.dbn.zst",
        sha256=digest((request.parent / "empty.dbn.zst").read_bytes()),
    )
    value["chunks"].append(empty)
    request.write_text(json.dumps(value))
    path = ingest(request, tmp_path / "data")
    receipts = json.loads((path / "receipts.json").read_text())["chunks"]
    assert receipts[-1]["status"] == "success_empty" and receipts[-1]["record_count"] == 0
    assert len(load_dataset(path).rows) == 2160
