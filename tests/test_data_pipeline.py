"""Independent native decoder/catalog/replay tests using generated DBN only."""

import copy
import json
from dataclasses import replace
from pathlib import Path

import pyarrow as pa
import pytest

from quantlab.data.core import coverage, normalize, snapshot
from quantlab.data.databento import decode, inspect_dbn
from quantlab.data.model import (
    MINUTE,
    SECOND,
    Config,
    DataError,
    digest,
    local_ns,
    same_contract_return,
    timestamp,
)
from quantlab.data.replay import replay_dataset
from quantlab.data.store import ingest, load_dataset
from quantlab.data.synthetic import write_dbn, write_demo


@pytest.fixture
def request_file(tmp_path: Path) -> Path:
    return write_demo(tmp_path / "inputs")


def change_config(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value))


def records(path: Path) -> list[tuple]:
    return [(instrument, start, *values) for _, instrument, start, values in inspect_dbn(path, 6)]


def rewrite(path: Path, rows: list[tuple], *, definitions: bool = False) -> dict:
    value = json.loads(path.read_text())
    name = "definitions.dbn.zst" if definitions else "bars.dbn.zst"
    write_dbn(path.parent / name, value["contracts"], rows, definitions=definitions)
    key = "definitions_sha256" if definitions else "sha256"
    value["chunks"][0][key] = digest((path.parent / name).read_bytes())
    change_config(path, value)
    return value


def normalized(path: Path):
    config = Config.parse(json.loads(path.read_text()))
    decoded, extra, _ = decode(config, path.parent)
    rows, duplicates = normalize(config, decoded)
    return config, rows, extra, duplicates


def test_native_definitions_bars_catalog_and_replay(request_file: Path, tmp_path: Path) -> None:
    config, rows, extra, duplicates = normalized(request_file)
    assert len(rows) == 2160
    assert duplicates == 0
    contract = extra["instruments"]["CME:MES:202212"]
    assert str(contract.id) == "MES-202212.CME"
    assert str(contract.price_increment) == "0.25"
    assert str(contract.multiplier) == "5"
    assert rows[0].start == local_ns("2022-11-21", "09:30")
    assert rows[0].end == rows[0].start + MINUTE
    assert rows[0].available == rows[0].end + SECOND
    published = ingest(request_file, tmp_path / "data")
    loaded = load_dataset(published)
    assert loaded.rows == rows
    assert len(loaded.bars) == 2160
    assert loaded.manifest["identity"]["software"]["lock_sha256"]
    assert loaded.manifest["identity"]["config"]["synthetic"] is True
    assert loaded.manifest["scope"] == "M2b.1 synthetic only"
    assert set(loaded.manifest["source_revision"]) == {"git_commit", "dirty"}
    assert len(loaded.endpoint_references()) == 40
    target = next(
        r for r in loaded.endpoint_references() if r["day"] == "2022-11-22" and r["name"] == "16:00"
    )
    assert target["role"] == "outcome"
    assert target["available_at_ns"] > local_ns("2022-11-22", "15:30") + SECOND
    assert set(loaded.manifest["files"]) >= {
        "provenance.parquet",
        "contracts.parquet",
        "sessions.parquet",
        "coverage.parquet",
        "quality.json",
        "receipts.json",
    }
    first = replay_dataset(published)
    assert first == replay_dataset(published)
    assert first["bars"] == first["iterations"] == 2160
    assert first["orders"] == first["positions"] == 0
    assert first["first_available_ns"] == rows[0].available
    assert first["last_available_ns"] == rows[-1].available
    assert config.payload["provider"] == "databento"


def test_publication_reuse_and_independent_rebuild(request_file: Path, tmp_path: Path) -> None:
    first = ingest(request_file, tmp_path / "a")
    before = {p: p.read_bytes() for p in first.rglob("*") if p.is_file()}
    assert ingest(request_file, tmp_path / "a") == first
    assert before == {p: p.read_bytes() for p in first.rglob("*") if p.is_file()}
    second = ingest(request_file, tmp_path / "b")
    assert first.name == second.name
    assert replay_dataset(first) == replay_dataset(second)


def test_latency_changes_version_and_replay_clock(request_file: Path, tmp_path: Path) -> None:
    first = ingest(request_file, tmp_path / "data")
    value = json.loads(request_file.read_text())
    value["delay_seconds"] = 60
    change_config(request_file, value)
    second = ingest(request_file, tmp_path / "data")
    assert first != second
    a, b = replay_dataset(first), replay_dataset(second)
    assert b["first_available_ns"] - a["first_available_ns"] == 59 * SECOND
    assert a["observations_sha256"] != b["observations_sha256"]


def test_exact_duplicates_and_out_of_order_are_audited(request_file: Path, tmp_path: Path) -> None:
    original = records(request_file.parent / "bars.dbn.zst")
    value = rewrite(request_file, list(reversed(original)) + [original[0]])
    overlap = request_file.parent / "overlap.dbn.zst"
    write_dbn(overlap, value["contracts"], original[:2])
    value["chunks"].append(
        dict(value["chunks"][0], path=overlap.name, sha256=digest(overlap.read_bytes()))
    )
    change_config(request_file, value)
    path = ingest(request_file, tmp_path / "data")
    loaded = load_dataset(path)
    assert len(loaded.rows) == len(original)
    assert len(loaded.rows[0].source_refs) == 3  # Two source ordinals plus the overlap.
    quality = json.loads((path / "quality.json").read_text())
    assert quality["duplicate_count"] == 3
    assert quality["out_of_order_count"] > 0
    assert replay_dataset(path)["orders"] == 0


def test_conflicting_revision_refuses_publication(request_file: Path, tmp_path: Path) -> None:
    original = records(request_file.parent / "bars.dbn.zst")
    conflict = list(original[0])
    conflict[5] += 250_000_000
    rewrite(request_file, original + [tuple(conflict)])
    with pytest.raises(DataError, match="conflicting duplicate"):
        ingest(request_file, tmp_path / "data")
    assert not list((tmp_path / "data").glob("curated/mes_itsm_v1/*/manifest.json"))


@pytest.mark.parametrize(
    "column,value",
    [(2, 0), (2, -(10**9)), (3, 4000 * 10**9), (4, 6000 * 10**9), (5, 5000 * 10**9 + 1)],
)
def test_raw_invalid_prices_rejected_before_precision_rounding(
    request_file: Path, tmp_path: Path, column: int, value: int
) -> None:
    original = records(request_file.parent / "bars.dbn.zst")
    invalid = list(original[0])
    invalid[column] = value
    rewrite(request_file, [tuple(invalid)])
    with pytest.raises(DataError, match="raw OHLC"):
        ingest(request_file, tmp_path / "data")


def test_zero_volume_cannot_supply_an_endpoint(request_file: Path) -> None:
    original = records(request_file.parent / "bars.dbn.zst")
    endpoint = local_ns("2022-11-22", "15:29")
    rewrite(request_file, [(*r[:-1], 0) if r[1] == endpoint else r for r in original])
    config, rows, _, _ = normalized(request_file)
    result = snapshot(config, rows, "2022-11-22", endpoint + MINUTE + SECOND)
    assert not result["inputs_ready"]
    assert "unavailable:15:30" in result["reasons"]


@pytest.mark.parametrize("kind", ["bad_zstd", "truncated", "missing_volume", "bad_schema"])
def test_corrupt_native_files_fail_closed(request_file: Path, tmp_path: Path, kind: str) -> None:
    path = request_file.parent / "bars.dbn.zst"
    if kind == "bad_zstd":
        path.write_bytes(b"not a DBN file")
    else:
        with pa.input_stream(str(path), compression="zstd") as stream:
            data = bytearray(stream.read())
        if kind == "bad_schema":
            data[24:26] = (5).to_bytes(2, "little")
        else:
            data = data[:-1] if kind == "truncated" else data[:-8]
        path.write_bytes(pa.compress(data, codec="zstd").to_pybytes())
    value = json.loads(request_file.read_text())
    value["chunks"][0]["sha256"] = digest(path.read_bytes())
    change_config(request_file, value)
    with pytest.raises(DataError):
        ingest(request_file, tmp_path / "data")


def test_unknown_publisher_and_mixed_contract_cannot_be_relabelled(
    request_file: Path, tmp_path: Path
) -> None:
    path = request_file.parent / "bars.dbn.zst"
    with pa.input_stream(str(path), compression="zstd") as stream:
        data = bytearray(stream.read())
    offset = 8 + int.from_bytes(data[4:8], "little")
    data[offset + 4 : offset + 8] = (999).to_bytes(4, "little")
    path.write_bytes(pa.compress(data, codec="zstd").to_pybytes())
    value = json.loads(request_file.read_text())
    value["chunks"][0]["sha256"] = digest(path.read_bytes())
    change_config(request_file, value)
    with pytest.raises(DataError, match="unknown raw"):
        ingest(request_file, tmp_path / "data")


def test_native_definition_must_match_expected_metadata(request_file: Path, tmp_path: Path) -> None:
    value = json.loads(request_file.read_text())
    value["contracts"][0]["raw_symbol"] = "MESZ22"  # Valid alias, different from file metadata.
    change_config(request_file, value)
    with pytest.raises(DataError, match="definition disagrees"):
        ingest(request_file, tmp_path / "data")


def test_changed_raw_bytes_and_escaping_source_paths_are_rejected(
    request_file: Path, tmp_path: Path
) -> None:
    (request_file.parent / "bars.dbn.zst").write_bytes(b"corrupt")
    with pytest.raises(DataError, match="checksum"):
        ingest(request_file, tmp_path / "data")
    value = json.loads(request_file.read_text())
    value["chunks"][0]["path"] = "../outside.dbn.zst"
    change_config(request_file, value)
    with pytest.raises(DataError, match="configuration"):
        ingest(request_file, tmp_path / "data")


@pytest.mark.parametrize("name", ["provenance.parquet", "quality.json", "coverage.parquet"])
def test_stored_tampering_is_detected(request_file: Path, tmp_path: Path, name: str) -> None:
    path = ingest(request_file, tmp_path / "data")
    (path / name).write_bytes(b"changed")
    with pytest.raises(DataError, match="checksum"):
        load_dataset(path)
    with pytest.raises(DataError):
        ingest(request_file, tmp_path / "data")


def test_raw_archive_and_inventory_tampering_are_detected(
    request_file: Path, tmp_path: Path
) -> None:
    root = tmp_path / "data"
    path = ingest(request_file, root)
    next((root / "raw").rglob("*.zst")).write_bytes(b"changed")
    with pytest.raises(DataError, match="raw provenance"):
        load_dataset(path)


def test_crash_before_publish_leaves_no_published_dataset(
    request_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import quantlab.data.store as storage

    original = storage._write_table

    def crash(path, rows):
        original(path, rows)
        raise RuntimeError("injected failure")

    monkeypatch.setattr(storage, "_write_table", crash)
    root = tmp_path / "data"
    with pytest.raises(RuntimeError, match="injected"):
        ingest(request_file, root)
    assert not list(root.glob("curated/mes_itsm_v1/*/manifest.json"))
    assert not list(root.glob("curated/mes_itsm_v1/.staging-*"))


def test_partial_staging_and_publication_flag_cannot_be_loaded(
    request_file: Path, tmp_path: Path
) -> None:
    partial = tmp_path / ".staging-partial"
    partial.mkdir()
    with pytest.raises(DataError, match="published"):
        load_dataset(partial)
    path = ingest(request_file, tmp_path / "data")
    manifest = json.loads((path / "manifest.json").read_text())
    manifest["complete"] = False
    (path / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(DataError, match="publication"):
        load_dataset(path)


def test_same_contract_returns_require_available_inputs(request_file: Path) -> None:
    _, rows, _, _ = normalized(request_file)
    assert same_contract_return(rows[0], rows[1], rows[1].available) == 0
    with pytest.raises(DataError, match="unavailable"):
        same_contract_return(rows[0], rows[1], rows[1].available - 1)
    with pytest.raises(DataError, match="boundaries"):
        same_contract_return(
            rows[0], replace(rows[1], contract="CME:MES:202303"), rows[1].available
        )


def test_later_missing_target_does_not_rewrite_earlier_input_snapshot(request_file: Path) -> None:
    config, rows, _, _ = normalized(request_file)
    day = "2022-11-22"
    asof = local_ns(day, "15:30") + SECOND
    original = snapshot(config, rows, day, asof)
    assert original["inputs_ready"]
    assert "16:00" not in original["values"]
    assert not snapshot(config, rows, day, asof - 1)["inputs_ready"]
    without_target = [r for r in rows if r.end != local_ns(day, "16:00")]
    assert snapshot(config, without_target, day, asof) == original
    assert snapshot(config, without_target, day, asof + 3600 * SECOND) == original
    report = next(c for c in coverage(config, without_target) if c["day"] == day)
    assert report["inputs_ready"] is True
    assert report["outcome_status"] == "unresolved"
    assert report["unknown_gap_count"] == 1
    assert not report["data_complete"]


def test_no_stale_or_next_bucket_substitution(request_file: Path) -> None:
    config, rows, _, _ = normalized(request_file)
    day = "2022-11-22"
    missing = [r for r in rows if r.end != local_ns(day, "10:00")]
    result = snapshot(config, missing, day, local_ns(day, "15:30") + SECOND)
    assert "unavailable:10:00" in result["reasons"]
    assert not result["inputs_ready"]


def test_calendar_closed_early_and_previous_early_are_separate(request_file: Path) -> None:
    config, rows, _, _ = normalized(request_file)
    for day, reason in [
        ("2022-11-24", "cash_closed"),
        ("2022-11-25", "early_close"),
        ("2022-11-28", "previous_early_close"),
    ]:
        result = snapshot(config, rows, day, local_ns(day, "15:30") + SECOND)
        assert not result["inputs_ready"]
        assert reason in result["reasons"]
    assert snapshot(config, rows, "2022-11-29", local_ns("2022-11-29", "15:30") + SECOND)[
        "inputs_ready"
    ]


def test_overnight_trade_date_is_not_utc_or_cash_date(request_file: Path) -> None:
    config, _, _, _ = normalized(request_file)
    start = local_ns("2022-11-21", "18:00")
    assert config.session_for(start, start + MINUTE).day == "2022-11-22"
    with pytest.raises(DataError, match="CME"):
        config.session_for(local_ns("2022-11-22", "17:30"), local_ns("2022-11-22", "17:31"))


def test_late_data_and_request_overflow_fail_closed(request_file: Path, tmp_path: Path) -> None:
    original = records(request_file.parent / "bars.dbn.zst")
    modified = list(original[0])
    modified[1] = local_ns("2022-12-01", "09:30")
    rewrite(request_file, [tuple(modified)])
    with pytest.raises(DataError, match="requested chunk"):
        ingest(request_file, tmp_path / "data")


@pytest.mark.parametrize(
    "field,value",
    [
        ("mode", "download"),
        ("synthetic", False),
        ("provider", "ibkr"),
        ("dataset", "OTHER"),
        ("schema", "trades"),
        ("delay_seconds", -1),
        ("delay_seconds", True),
        ("delay_seconds", 61),
        ("rights_ref", "vendor:unapproved"),
        ("start", "2022-12-01T00:00:00Z"),
        ("calendar_version", "https://secret.example/?key=invalid"),
    ],
)
def test_unsupported_and_unsafe_configuration(
    request_file: Path, field: str, value: object
) -> None:
    config = json.loads(request_file.read_text())
    config[field] = value
    with pytest.raises(ValueError):
        Config.parse(config)


@pytest.mark.parametrize(
    "change",
    [
        "unknown_field",
        "missing_contract",
        "wrong_tick",
        "wrong_currency",
        "wrong_expiry",
        "duplicate_contract",
        "naive_time",
        "partial_calendar",
        "overlap_calendar",
        "wider_chunk",
    ],
)
def test_invalid_metadata_and_boundaries(request_file: Path, change: str) -> None:
    value = json.loads(request_file.read_text())
    if change == "unknown_field":
        value["api_key"] = "MUST_NOT_BE_PERSISTED"
    elif change == "missing_contract":
        value["contracts"] = []
    elif change == "wrong_tick":
        value["contracts"][0]["tick"] = "0.01"
    elif change == "wrong_currency":
        value["contracts"][0]["currency"] = "EUR"
    elif change == "wrong_expiry":
        value["contracts"][0]["expiration"] = "2023-03-17T13:30:00Z"
    elif change == "duplicate_contract":
        value["contracts"] *= 2
    elif change == "naive_time":
        value["contracts"][0]["expiration"] = "2022-12-16T14:30:00"
    elif change == "partial_calendar":
        del value["sessions"][1]
    elif change == "overlap_calendar":
        value["sessions"][1]["cme_intervals"] = copy.deepcopy(value["sessions"][0]["cme_intervals"])
    elif change == "wider_chunk":
        value["chunks"][0]["end"] = "2023-01-01T00:00:00Z"
    with pytest.raises(ValueError):
        Config.parse(value)


@pytest.mark.parametrize(
    "value",
    [
        "1900-01-01T00:00:00Z",
        "2022-01-01T00:00:00.000000001Z",
        "2022-01-01T00:00:00",
        "2022-03-13T02:30:00",  # Impossible New York wall time, without an offset.
        "2022-11-06T01:30:00",  # Ambiguous New York wall time, without an offset.
        "9999-01-01T00:00:00Z",
    ],
)
def test_unsupported_timestamp_precision_range_and_naive_values(value: str) -> None:
    with pytest.raises(DataError, match="timestamp"):
        timestamp(value)


@pytest.mark.parametrize("bad_volume", [-1, 1.5, True, "10"])
def test_provider_neutral_core_rejects_bad_volume(request_file: Path, bad_volume) -> None:
    config = Config.parse(json.loads(request_file.read_text()))
    decoded, _, _ = decode(config, request_file.parent)
    with pytest.raises(DataError, match="volume"):
        normalize(config, [replace(decoded[0], volume=bad_volume)])


def test_source_symlink_cannot_escape_input_directory(request_file: Path, tmp_path: Path) -> None:
    outside = tmp_path / "external.dbn.zst"
    outside.write_bytes((request_file.parent / "bars.dbn.zst").read_bytes())
    (request_file.parent / "link.dbn.zst").symlink_to(outside)
    value = json.loads(request_file.read_text())
    value["chunks"][0]["path"] = "link.dbn.zst"
    change_config(request_file, value)
    with pytest.raises(DataError, match="escapes"):
        ingest(request_file, tmp_path / "data")


def test_normalized_row_change_creates_new_version(request_file: Path, tmp_path: Path) -> None:
    first = ingest(request_file, tmp_path / "data")
    original = records(request_file.parent / "bars.dbn.zst")
    modified = list(original[0])
    modified[5] += 250_000_000
    rewrite(request_file, [tuple(modified), *original[1:]])
    second = ingest(request_file, tmp_path / "data")
    assert first.name != second.name
    assert load_dataset(first).rows[0].close != load_dataset(second).rows[0].close


def test_receipts_are_local_not_fabricated_vendor_delivery(
    request_file: Path, tmp_path: Path
) -> None:
    path = ingest(request_file, tmp_path / "data")
    receipts = json.loads((path / "receipts.json").read_text())
    assert receipts["vendor_retrieved_at"] is None
    assert timestamp(receipts["ingested_at_utc"]) > 0
    assert set(receipts) == {"ingested_at_utc", "vendor_retrieved_at", "chunks"}
