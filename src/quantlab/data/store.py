"""Content-addressed raw inputs and verified, atomic native Parquet datasets."""

import json
import os
import platform
import re
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from importlib.metadata import version
from importlib.resources import files
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
from nautilus_trader.persistence.catalog.parquet import ParquetDataCatalog

from quantlab.data.core import (
    coverage,
    endpoint_references,
    native_bar,
    normalize,
    provenance,
    snapshot,
)
from quantlab.data.databento import decode
from quantlab.data.model import TZ_VERSION, Config, DataError, Observation, canonical, digest


def software() -> dict[str, Any]:
    directory = Path(__file__).parent
    source = b"".join(p.name.encode() + p.read_bytes() for p in sorted(directory.glob("*.py")))
    lock = directory.parents[2] / "uv.lock"
    packaged_lock = files("quantlab").joinpath("uv.lock")
    lock_bytes = (
        lock.read_bytes()
        if lock.is_file()
        else (packaged_lock.read_bytes() if packaged_lock.is_file() else None)
    )
    return {
        "code_sha256": digest(source),
        "lock_sha256": digest(lock_bytes) if lock_bytes is not None else None,
        "nautilus": version("nautilus-trader"),
        "arrow": version("pyarrow"),
        "python": platform.python_version(),
        "tzdata": TZ_VERSION,
        "quantlab": version("quantlab"),
    }


def safe_file(root: Path, relative: str) -> Path:
    p = root / relative
    if (
        Path(relative).is_absolute()
        or ".." in Path(relative).parts
        or p.is_symlink()
        or not p.resolve().is_relative_to(root.resolve())
    ):
        raise DataError("dataset file escapes storage root")
    return p


def source_revision() -> dict[str, Any]:
    """Optional checkout trace; content identity always uses actual code hashes."""
    root = Path(__file__).parent.parents[2]
    if not (root / ".git").exists():
        return {"git_commit": None, "dirty": None}
    try:
        command = ["git", "--no-optional-locks", "-C", str(root)]
        commit = (
            subprocess.check_output(
                command + ["rev-parse", "HEAD"], stderr=subprocess.DEVNULL, timeout=3
            )
            .decode()
            .strip()
        )
        dirty = bool(
            subprocess.check_output(
                command + ["status", "--porcelain"], stderr=subprocess.DEVNULL, timeout=3
            )
        )
        return {"git_commit": commit, "dirty": dirty}
    except (OSError, subprocess.SubprocessError):
        return {"git_commit": None, "dirty": None}


def _write_table(path: Path, rows: list[dict[str, Any]]) -> None:
    pq.write_table(pa.Table.from_pylist(rows), path, compression="zstd")


def ingest(request: Path, output: Path) -> Path:
    if request.stat().st_size > 1024 * 1024:
        raise DataError("request exceeds size limit")
    try:
        config = Config.parse(json.loads(request.read_text()))
    except (ValueError, TypeError, KeyError, OverflowError):
        raise DataError("invalid offline configuration") from None
    records, extra, raw_files = decode(config, request.parent)
    rows, duplicates = normalize(config, records)
    if not rows:
        raise DataError("empty dataset; receipts cannot be published as replay data")
    identity = {"config": config.payload, "software": software(), "raw_hashes": sorted(raw_files)}
    dataset_id = digest(canonical(identity))
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with publication_lock(output, dataset_id):
        return _publish(config, output, identity, rows, duplicates, extra, raw_files)


@contextmanager
def publication_lock(output: Path, dataset_id: str) -> Iterator[None]:
    """Exclusive writer; a crash lock requires explicit operator investigation."""
    lock = output / f".publish-{dataset_id}.lock"
    try:
        stream = lock.open("x")
    except FileExistsError:
        raise DataError("publication already locked; verify writer before recovery") from None
    try:
        with stream:
            stream.write(str(os.getpid()))
            stream.flush()
            os.fsync(stream.fileno())
            yield
    finally:
        lock.unlink()


def _publish(
    config: Config,
    output: Path,
    identity: dict[str, Any],
    rows: list[Observation],
    duplicates: int,
    extra: dict[str, Any],
    raw_files: dict[str, bytes],
) -> Path:
    dataset_id = digest(canonical(identity))
    final = output / "curated" / "mes_itsm_v1" / dataset_id
    if final.exists():
        load_dataset(final)
        return final
    raw_root = output / "raw" / "databento" / "GLBX.MDP3"
    raw_root.mkdir(parents=True, exist_ok=True)
    for checksum, data in raw_files.items():
        path = safe_file(raw_root, checksum + ".dbn.zst")
        descriptor, temporary = tempfile.mkstemp(prefix=".raw-", dir=raw_root)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, path)
            except FileExistsError:
                if digest(path.read_bytes()) != checksum:
                    raise DataError("raw archive hash conflict") from None
        finally:
            Path(temporary).unlink()
    final.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=final.parent))
    try:
        catalog = ParquetDataCatalog(str(staging / "catalog"))
        catalog.write_data(list(extra["instruments"].values()))
        catalog.write_data([native_bar(r) for r in rows])
        _write_table(staging / "provenance.parquet", provenance(rows, extra["source"]))
        _write_table(
            staging / "contracts.parquet",
            [
                asdict(c)
                | {
                    "canonical_contract": c.key,
                    "native_id": c.native_id,
                    "currency": "USD",
                    "tick": "0.25",
                    "multiplier": 5,
                    "exchange": "XCME",
                }
                for c in config.contracts
            ],
        )
        _write_table(
            staging / "sessions.parquet",
            [
                {
                    "day": s.day,
                    "cash_close": s.cash_close,
                    "cme_intervals_json": canonical(s.intervals).decode(),
                    "calendar_version": config.payload["calendar_version"],
                    "roll_version": config.payload["roll_version"],
                }
                for s in config.sessions
            ],
        )
        _write_table(staging / "coverage.parquet", coverage(config, rows))
        _write_table(staging / "endpoints.parquet", endpoint_references(config, rows))
        (staging / "quality.json").write_bytes(
            canonical(
                {
                    "synthetic": True,
                    "records": len(rows),
                    "duplicate_count": duplicates,
                    "out_of_order_count": extra["reordered"],
                    "revision_policy": "reject_conflicts",
                    "gap_policy": "unknown_no_padding",
                }
            )
        )
        (staging / "receipts.json").write_bytes(
            canonical(
                {
                    "ingested_at_utc": datetime.now(UTC).isoformat(),
                    "vendor_retrieved_at": None,
                    "chunks": extra["receipts"],
                }
            )
        )
        hashes = {
            str(p.relative_to(staging)): digest(p.read_bytes())
            for p in staging.rglob("*")
            if p.is_file()
        }
        manifest = {
            "complete": True,
            "dataset_version": dataset_id,
            "identity": identity,
            "files": hashes,
            "logical_rows_sha256": digest(canonical([asdict(r) for r in rows])),
            "record_count": len(rows),
            "scope": "M2b.1 synthetic only",
            "rights_ref": config.payload["rights_ref"],
            "source_revision": source_revision(),
        }
        (staging / "manifest.json").write_bytes(canonical(manifest))
        loaded = _read(staging, manifest, config)
        if loaded.rows != rows:
            raise DataError("native catalog round-trip differs from normalized observations")
        for p in staging.rglob("*"):
            if p.is_file():
                with p.open("rb") as stream:
                    os.fsync(stream.fileno())
        try:
            staging.rename(final)
        except FileExistsError:
            load_dataset(final)
        return final
    finally:
        if staging.exists():
            shutil.rmtree(staging)


class Dataset:
    def __init__(
        self,
        path: Path,
        manifest: dict[str, Any],
        config: Config,
        rows: list[Observation],
        bars: list[Any],
        instruments: list[Any],
    ) -> None:
        self.path, self.manifest, self.config = path, manifest, config
        self.rows, self.bars, self.instruments = rows, bars, instruments

    def snapshot(self, day: str, asof_ns: int) -> dict[str, Any]:
        return snapshot(self.config, self.rows, day, asof_ns)

    def coverage(self) -> list[dict[str, Any]]:
        return coverage(self.config, self.rows)

    def endpoint_references(self) -> list[dict[str, Any]]:
        return endpoint_references(self.config, self.rows)


def _read(path: Path, manifest: dict[str, Any], config: Config) -> Dataset:
    declared = manifest["files"]
    actual = {
        str(p.relative_to(path))
        for p in path.rglob("*")
        if p.is_file() and p.name != "manifest.json"
    }
    if actual != set(declared):
        raise DataError("dataset file inventory differs from manifest")
    for name, checksum in declared.items():
        p = safe_file(path, name)
        if digest(p.read_bytes()) != checksum:
            raise DataError("dataset file checksum mismatch")
    catalog = ParquetDataCatalog(str(path / "catalog"))
    instruments = catalog.instruments()
    bars = sorted(
        catalog.bars(), key=lambda b: (b.ts_init, str(b.bar_type.instrument_id), b.ts_event)
    )
    sidecars = pq.read_table(path / "provenance.parquet").to_pylist()
    by_key = {(p["contract"], p["end"]): p for p in sidecars}
    if len(by_key) != len(sidecars) or len(sidecars) != len(bars):
        raise DataError("native rows and provenance are not one-to-one")
    rows = []
    for b in bars:
        month = str(b.bar_type.instrument_id.symbol).removeprefix("MES-")
        key = (f"CME:MES:{month}", b.ts_event)
        provenance_row = by_key.get(key)
        if (
            provenance_row is None
            or provenance_row["available"] != b.ts_init
            or provenance_row["start"] + 60_000_000_000 != b.ts_event
        ):
            raise DataError("native time/identity disagrees with provenance")
        rows.append(
            Observation(
                key[0],
                provenance_row["start"],
                b.ts_event,
                b.ts_init,
                str(b.open),
                str(b.high),
                str(b.low),
                str(b.close),
                int(b.volume.as_decimal()),
                provenance_row["exchange_trade_date"],
                tuple(provenance_row["source_refs"]),
            )
        )
    if (
        len(rows) != manifest["record_count"]
        or digest(canonical([asdict(r) for r in rows])) != manifest["logical_rows_sha256"]
    ):
        raise DataError("logical dataset hash mismatch")
    return Dataset(path, manifest, config, rows, bars, instruments)


def load_dataset(path: Path) -> Dataset:
    if path.is_symlink() or not re.fullmatch(r"[a-f0-9]{64}", path.name):
        raise DataError("only immutable published dataset IDs can be loaded")
    try:
        if (path / "manifest.json").stat().st_size > 4 * 1024 * 1024:
            raise DataError("manifest exceeds size limit")
        manifest = json.loads((path / "manifest.json").read_text())
        if (
            manifest["complete"] is not True
            or manifest["dataset_version"] != path.name
            or digest(canonical(manifest["identity"])) != path.name
        ):
            raise DataError("invalid publication identity")
        if manifest["identity"]["software"]["nautilus"] != version("nautilus-trader"):
            raise DataError("catalog framework version mismatch")
        config = Config.parse(manifest["identity"]["config"])
        for checksum in manifest["identity"]["raw_hashes"]:
            if not re.fullmatch(r"[a-f0-9]{64}", checksum):
                raise DataError("invalid raw content address")
            raw = safe_file(
                path.parents[2] / "raw" / "databento" / "GLBX.MDP3", checksum + ".dbn.zst"
            )
            if digest(raw.read_bytes()) != checksum:
                raise DataError("raw provenance checksum mismatch")
        return _read(path, manifest, config)
    except DataError:
        raise
    except Exception:
        raise DataError("invalid or incomplete stored dataset") from None
