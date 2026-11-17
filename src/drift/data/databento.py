"""Local DBN adapter. Native Nautilus decodes both definitions and prices."""

import json
import struct
from decimal import Decimal
from pathlib import Path
from typing import Any

import pyarrow as pa
from nautilus_trader.adapters.databento.constants import PUBLISHERS_FILEPATH
from nautilus_trader.adapters.databento.loaders import DatabentoDataLoader
from nautilus_trader.model.enums import AssetClass
from nautilus_trader.model.instruments import FuturesContract

from drift.data.model import MINUTE, Config, DataError, SourceBar, digest

MAX_FILE_BYTES = 32 * 1024 * 1024
MAX_RECORDS = 100_000


def read_source(root: Path, name: str, checksum: str) -> bytes:
    path = root / name
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        raise DataError("source path escapes local input directory")
    if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
        raise DataError("source missing or exceeds chunk size limit")
    data = path.read_bytes()
    if digest(data) != checksum:
        raise DataError("source checksum mismatch")
    return data


def inspect_dbn(path: Path, schema: int) -> list[tuple[int, int, int, tuple[int, ...]]]:
    """Bounded framing/identity audit, not a replacement price/definition decoder.

    Check raw IDs and 1e-9 price integers before native precision conversion can
    round invalid input. Compressed DBN is required by the pinned file loader.
    """
    try:
        with pa.input_stream(str(path), compression="zstd") as stream:
            prefix = stream.read(8)
            if len(prefix) != 8 or prefix[:3] != b"DBN" or prefix[3] not in (1, 2, 3):
                raise DataError("unsupported DBN framing/version")
            size = struct.unpack_from("<I", prefix, 4)[0]
            if not 100 <= size <= 1024 * 1024:
                raise DataError("invalid DBN metadata size")
            metadata = stream.read(size)
            if len(metadata) != size or metadata[:16].rstrip(b"\0") != b"GLBX.MDP3":
                raise DataError("DBN dataset mismatch")
            if (
                struct.unpack_from("<H", metadata, 16)[0] != schema
                or metadata[52 if prefix[3] == 1 else 44]
            ):
                raise DataError("DBN schema/ts_out is unsupported")
            result: list[tuple[int, int, int, tuple[int, ...]]] = []
            total = size + 8
            while first := stream.read(1):
                length = first[0] * 4
                if length < 16 or length > 4096:
                    raise DataError("invalid DBN record length")
                row = first + stream.read(length - 1)
                total += length
                if len(row) != length or total > MAX_FILE_BYTES or len(result) >= MAX_RECORDS:
                    raise DataError("truncated DBN or decoded chunk limit exceeded")
                _, rtype, publisher, instrument, event = struct.unpack_from("<BBHIQ", row)
                if rtype != (0x21 if schema == 6 else 0x13):
                    raise DataError("unexpected DBN record type")
                values: tuple[int, ...] = ()
                if schema == 6:
                    if length != 56:
                        raise DataError("unexpected OHLCV record length")
                    values = struct.unpack_from("<qqqqQ", row, 16)
                    op, hi, lo, cl, volume = values
                    if (
                        any(v <= 0 or v % 250_000_000 for v in (op, hi, lo, cl))
                        or not lo <= min(op, cl) <= max(op, cl) <= hi
                    ):
                        raise DataError("invalid raw OHLC/tick values")
                result.append((publisher, instrument, event, values))
            return result
    except DataError:
        raise
    except Exception:
        raise DataError("DBN framing/decompression failed") from None


def decode(config: Config, root: Path) -> tuple[list[SourceBar], dict[str, Any], dict[str, bytes]]:
    mapping = {(c.publisher_id, c.provider_id): c for c in config.contracts}
    publishers = {
        p["publisher_id"]: p["dataset"] for p in json.loads(PUBLISHERS_FILEPATH.read_text())
    }
    if any(publishers.get(c.publisher_id) != config.payload["dataset"] for c in config.contracts):
        raise DataError("publisher does not belong to the requested dataset")
    decoded = []
    instruments: dict[str, Any] = {}
    raw_files = {}
    receipts = []
    reordered = 0
    for chunk in config.chunks:
        for name, checksum in (
            (chunk.path, chunk.sha256),
            (chunk.definitions, chunk.definitions_sha256),
        ):
            raw_files[checksum] = read_source(root, name, checksum)
        definition_headers = inspect_dbn(root / chunk.definitions, 9)
        headers = inspect_dbn(root / chunk.path, 6)
        if any(h[:2] not in mapping for h in headers + definition_headers):
            raise DataError("unknown raw provider/publisher identity")
        loader = DatabentoDataLoader()
        try:
            definitions = loader.from_dbn_file(root / chunk.definitions, skip_on_error=False)
            bars = loader.from_dbn_file(
                root / chunk.path,
                price_precision=2,
                bars_timestamp_on_close=True,
                skip_on_error=False,
            )
        except Exception:
            raise DataError("native DBN decoding failed") from None
        if len(definitions) != len(definition_headers) or len(bars) != len(headers):
            raise DataError("native decoder dropped records")
        chunk_contracts = set()
        for header, native in zip(definition_headers, definitions, strict=True):
            contract = mapping.get(header[:2])
            if contract is None or not isinstance(native, FuturesContract):
                raise DataError("unknown source contract or non-future definition")
            expected = (
                contract.raw_symbol,
                "USD",
                "XCME",
                contract.activation,
                contract.expiration,
                Decimal("0.25"),
                Decimal(5),
                Decimal(1),
                AssetClass.INDEX,
            )
            actual = (
                str(native.raw_symbol),
                str(native.quote_currency),
                str(native.exchange),
                native.activation_ns,
                native.expiration_ns,
                native.price_increment.as_decimal(),
                native.multiplier.as_decimal(),
                native.lot_size.as_decimal(),
                native.asset_class,
            )
            if actual != expected:
                raise DataError("native definition disagrees with contract mapping")
            if native.ts_init > chunk.start:
                raise DataError("definition was not available at chunk start")
            row = FuturesContract.to_dict(native)
            row["id"] = contract.native_id
            row["info"] = {"synthetic": True, "canonical_contract": contract.key}
            replacement = FuturesContract.from_dict(row)
            if (
                contract.key in instruments
                and FuturesContract.to_dict(instruments[contract.key]) != row
            ):
                raise DataError("conflicting contract definition revision")
            instruments[contract.key] = replacement
            chunk_contracts.add(contract.key)
        previous = -1
        for offset, (header, bar) in enumerate(zip(headers, bars, strict=True)):
            publisher, provider_id, start, values = header
            c = mapping.get((publisher, provider_id))
            if (
                c is None
                or c.key not in chunk_contracts
                or str(bar.bar_type.instrument_id.symbol) != c.raw_symbol
            ):
                raise DataError("unknown or mixed contract identity")
            if not chunk.start <= start < start + MINUTE <= chunk.end or start % MINUTE:
                raise DataError("bar outside requested chunk or off-minute timestamp")
            if not c.activation <= start < start + MINUTE <= c.expiration:
                raise DataError("bar outside contract lifetime")
            if bar.ts_event != start + MINUTE:
                raise DataError("native timestamp conversion did not shift exactly once")
            prices = tuple(str(p) for p in (bar.open, bar.high, bar.low, bar.close))
            if (
                tuple(Decimal(p) * 10**9 for p in prices) != values[:4]
                or bar.volume.as_decimal() != values[4]
            ):
                raise DataError("native conversion lost price/volume precision")
            reordered += start < previous
            previous = start
            decoded.append(
                SourceBar(
                    c,
                    start,
                    (prices[0], prices[1], prices[2], prices[3]),
                    values[4],
                    f"{chunk.sha256}:{offset}",
                )
            )
            if len(decoded) > 250_000:
                raise DataError("offline dataset exceeds 250000-row memory bound")
        receipts.append(
            {
                "raw_hash": chunk.sha256,
                "definitions_hash": chunk.definitions_sha256,
                "start": chunk.start,
                "end": chunk.end,
                "record_count": len(headers),
                "status": "success" if headers else "success_empty",
            }
        )
    if set(instruments) != {c.key for c in config.contracts}:
        raise DataError("declared contract definitions are incomplete")
    return (
        decoded,
        {
            "instruments": instruments,
            "receipts": receipts,
            "reordered": reordered,
            "source": {
                "provider": "databento",
                "dataset": "GLBX.MDP3",
                "schema": "ohlcv-1m",
                "aggregation_clock": "provider_receive",
            },
        },
        raw_files,
    )
