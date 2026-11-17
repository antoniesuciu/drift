"""Private immutable Alpaca receipts and native Parquet, with raw-to-catalog verification."""

import json
import os
import resource
import shutil
import tempfile
import time
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any
from uuid import uuid4

import pyarrow as pa
import pyarrow.parquet as pq
from nautilus_trader.persistence.catalog.parquet import ParquetDataCatalog

from drift.backtest.data import MarketData, native_bars
from drift.backtest.engine import make_instrument
from drift.backtest.engine import software as backtest_software
from drift.data.alpaca import AlpacaClient, Receipt
from drift.data.equity import PilotRequest, calendar_from, identity, normalize, split_evidence
from drift.data.model import DataError, canonical, digest
from drift.data.store import publication_lock, safe_file, software, source_revision


def analysis_table(data: MarketData) -> Any:
    """Plain typed OHLCV for SQL; native Nautilus encoding remains the engine format."""
    schema = pa.schema(
        [(k, pa.int64()) for k in ("start_ns", "end_ns", "available_ns")]
        + [("session_date", pa.string())]
        + [
            (k, pa.decimal128(24, data.instrument.precision))
            for k in ("open", "high", "low", "close")
        ]
        + [("volume", pa.int64()), ("instrument_id", pa.string()), ("feed", pa.string())]
    )
    rows = [
        dict(
            start_ns=c.start,
            end_ns=c.end,
            available_ns=c.available,
            session_date=c.day,
            open=c.open,
            high=c.high,
            low=c.low,
            close=c.close,
            volume=c.volume,
            instrument_id=data.instrument.id,
            feed=data.source_feed,
        )
        for c in data.candles
    ]
    return pa.Table.from_pylist(rows, schema=schema)


def _write(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(body)
        stream.flush()
        os.fsync(stream.fileno())


def _receipt(root: Path, receipt: Receipt) -> dict[str, Any]:
    evidence = receipt.evidence()
    relative = f"raw/{evidence['sha256']}.json"
    path = root / relative
    if path.exists():
        if digest(path.read_bytes()) != evidence["sha256"]:
            raise DataError("raw receipt hash conflict")
    else:
        _write(path, receipt.body)
    return evidence | {"file": relative}


def _read_receipt(root: Path, raw: dict[str, Any]) -> Receipt:
    body = safe_file(root, raw["file"]).read_bytes()
    if digest(body) != raw["sha256"]:
        raise DataError("raw receipt checksum mismatch")
    return Receipt(
        raw["stream"], raw["params"], body, raw["observed_at"], raw["headers"], raw["endpoint"]
    )


def publish(request: PilotRequest, receipts: list[Receipt], output: Path) -> Path:
    """Only exhaustive, valid requests publish; gaps remain explicit and never get padded."""
    versions = software() | {"consumer_code_sha256": backtest_software()["code_sha256"]}
    dataset_id = identity(request, receipts, versions)
    data, quality = normalize(request, receipts, source_ref=dataset_id)
    output.mkdir(parents=True, exist_ok=True)
    with publication_lock(output, dataset_id):
        final = output / "curated" / dataset_id
        if final.exists():
            load(final)
            return final
        final.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=".equity-", dir=final.parent))
        try:
            evidence = [_receipt(staging, r) for r in receipts]
            catalog = ParquetDataCatalog(str(staging / "catalog"))
            catalog.write_data([make_instrument(data.instrument)])
            catalog.write_data(native_bars(data))
            pq.write_table(analysis_table(data), staging / "bars.parquet", compression="zstd")
            _write(staging / "quality.json", canonical(quality))
            inventory = {
                str(p.relative_to(staging)): digest(p.read_bytes())
                for p in sorted(staging.rglob("*"))
                if p.is_file()
            }
            manifest = {
                "version": 1,
                "dataset_id": dataset_id,
                "provider": "alpaca",
                "request": asdict(request),
                "instrument": asdict(data.instrument) | {"tick": str(data.instrument.tick)},
                "receipts": evidence,
                "software": versions,
                "source_revision": source_revision(),
                "splits": split_evidence(request),
                "split_policy": "reviewed issuer split context; cash dividends unadjusted",
                "action_completeness": "not certified; no full corporate-action crawl",
                "rights": (
                    "user authorized private development research; account terms apply; "
                    "redistribution and indefinite retention unverified"
                ),
                "data_sha256": data.sha256,
                "inventory": inventory,
            }
            body = canonical(manifest)
            _write(staging / "manifest.json", body)
            _write(staging / "COMPLETE", digest(body).encode())
            load(staging)
            staging.rename(final)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
        return final


def load(root: Path) -> tuple[MarketData, dict[str, Any]]:
    """Verify every file, replay original responses and compare all native instrument/bar fields."""
    try:
        body = (root / "manifest.json").read_bytes()
        if (root / "COMPLETE").read_text() != digest(body):
            raise DataError("incomplete/corrupt equity publication")
        manifest = json.loads(body)
        if manifest["version"] != 1 or manifest["provider"] != "alpaca":
            raise DataError("unsupported equity dataset version/provider")
        expected = set(manifest["inventory"]) | {"manifest.json", "COMPLETE"}
        actual = {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()}
        if expected != actual:
            raise DataError("equity catalog inventory differs")
        for relative, checksum in manifest["inventory"].items():
            if digest(safe_file(root, relative).read_bytes()) != checksum:
                raise DataError("equity dataset checksum mismatch")
        request = PilotRequest(**manifest["request"])
        receipts = [_read_receipt(root, r) for r in manifest["receipts"]]
        dataset_id = identity(request, receipts, manifest["software"])
        if dataset_id != manifest["dataset_id"] or manifest["splits"] != split_evidence(request):
            raise DataError("equity dataset identity/action mismatch")
        data, quality = normalize(request, receipts, source_ref=dataset_id)
        instrument = asdict(data.instrument) | {"tick": str(data.instrument.tick)}
        if manifest["instrument"] != instrument:
            raise DataError("manifest instrument differs from normalized metadata")
        if (
            data.sha256 != manifest["data_sha256"]
            or json.loads((root / "quality.json").read_bytes()) != quality
        ):
            raise DataError("raw-to-normalized replay differs")
        catalog = ParquetDataCatalog(str(root / "catalog"))
        actual_bars = sorted(catalog.bars(), key=lambda b: b.ts_event)
        if actual_bars != native_bars(data) or catalog.instruments() != [
            make_instrument(data.instrument)
        ]:
            raise DataError("native catalog differs from raw reconstruction")
        if "bars.parquet" in manifest["inventory"] and not pq.ParquetFile(
            root / "bars.parquet"
        ).read().equals(analysis_table(data)):
            raise DataError("analytical Parquet differs from raw reconstruction")
        return data, manifest
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        raise DataError("invalid/incomplete equity dataset") from None


def backtest_template(root: Path) -> dict[str, Any]:
    """An explicit illustrative feasibility configuration, not a calibrated cost schedule."""
    from drift.backtest.config import default_config

    _, manifest = load(root)
    raw = default_config("itsm")
    raw.update(
        version=2,
        synthetic=False,
        name="nvda-itsm-feasibility",
        instrument=manifest["instrument"],
        data={"dataset_id": manifest["dataset_id"]},
        capital="10000",
    )
    raw["sizing"] = {"mode": "fixed_quantity", "amount": "1"}
    raw["risk"].update(max_quantity="1", max_notional="1000", max_leverage="1")
    raw["strategy"]["params"] = {
        "allow_short": False,  # No verified borrow assumptions; no short simulation by default.
        "splits": [[s["day"], s["ratio"]] for s in manifest["splits"]],
    }
    return raw


def acquire(
    request: PilotRequest,
    client: AlpacaClient,
    output: Path,
    *,
    check_storage: Callable[[int], None] | None = None,
) -> Path:
    """Resume completed session requests; an interrupted session restarts without data loss.

    Every successful page is retained before proceeding. Failed invocations preserve their
    receipts and sanitized request ledger under requests/, never as a complete publication.
    """
    started = time.monotonic()
    output.mkdir(parents=True, exist_ok=True)
    key = digest(canonical(asdict(request)))
    work = output / "requests" / key
    work.mkdir(parents=True, exist_ok=True)
    with publication_lock(work, key):

        def stream(name: str, query: dict[str, str | int]) -> list[Receipt]:
            cache = work / f"{name}.json"
            if cache.exists():
                return [_read_receipt(work, r) for r in json.loads(cache.read_bytes())]
            evidence = []

            def save(r: Receipt) -> None:
                if check_storage is not None:
                    check_storage(2 * len(r.body) + 65536)
                evidence.append(_receipt(work, r))

            if name.startswith("bars-"):
                receipts = client.pages(query, on_receipt=save)
            else:
                r = client.get(name, query)
                save(r)
                receipts = [r]
            _write(cache, canonical(evidence))
            return receipts

        try:
            calendar = stream(
                "calendar", {"start": request.start, "end": request.end, "date_type": "TRADING"}
            )
            sessions = calendar_from(request, calendar[0])
            receipts = calendar + stream("asset", {"symbol": request.instrument.symbol})
            for session in sessions.sessions:
                receipts += stream("bars-" + session.day, request.query(session))
            if check_storage is not None:
                check_storage(sum(len(r.body) for r in receipts) * 2 + 64 * 1024**2)
            return publish(request, receipts, output)
        finally:
            # Atomic replacement; old attempts/raw bytes are kept and never imply completeness.
            attempt = work / ("attempt-" + uuid4().hex + ".json")
            _write(
                attempt,
                canonical(
                    {
                        "requests": client.requests,
                        "elapsed_seconds": time.monotonic() - started,
                        "process_peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                    }
                ),
            )
