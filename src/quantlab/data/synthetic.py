"""Locally generated DBN fixtures, never exchange observations.

The small test encoder follows Databento's public DBN v1/v2 wire layouts
(dbn/rust/dbn/src/{compat.rs,encode/dbn/sync.rs}). Production decoding is
performed by Nautilus, not this encoder. No SDK, credentials or requests.
"""

import struct
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pyarrow as pa

from quantlab.data.model import MINUTE, canonical, digest, instant, local_ns, timestamp


def metadata(schema: int, contracts: list[dict[str, Any]], version: int = 2) -> bytes:
    width = 22 if version == 1 else 71
    body = b"GLBX.MDP3".ljust(16, b"\0") + struct.pack("<HQQQ", schema, 0, 2**64 - 1, 0)
    if version == 1:
        body += struct.pack("<Q", 2**64 - 1)
    body += bytes([1, 0, 0])
    body += bytes(47) if version == 1 else struct.pack("<H", width) + bytes(53)
    assert len(body) == 100
    body += struct.pack("<IIII", 0, 0, 0, 0) + struct.pack("<I", len(contracts))
    for c in contracts:
        body += c["raw_symbol"].encode().ljust(width, b"\0")
        body += struct.pack("<III", 1, 20200101, 20300101)
        body += str(c["provider_id"]).encode().ljust(width, b"\0")
    return b"DBN" + bytes([version]) + struct.pack("<I", len(body)) + body


def definition(c: dict[str, Any]) -> bytes:
    row = bytearray(360)
    struct.pack_into(
        "<BBHIQ", row, 0, 90, 0x13, c["publisher_id"], c["provider_id"], timestamp(c["activation"])
    )
    struct.pack_into(
        "<QqqQQ",
        row,
        16,
        timestamp(c["activation"]),
        250_000_000,
        10**9,
        timestamp(c["expiration"]),
        timestamp(c["activation"]),
    )
    struct.pack_into("<q", row, 88, 5 * 10**9)
    struct.pack_into("<i", row, 148, 1)
    struct.pack_into("<i", row, 160, 5)
    struct.pack_into("<H", row, 180, int(c["month"][:4]))
    for offset, width, text in [
        (186, 4, "USD"),
        (190, 4, "USD"),
        (200, 22, c["raw_symbol"]),
        (222, 21, "MES"),
        (243, 5, "XCME"),
        (248, 7, "MES"),
        (255, 7, "FFICSX"),
        (262, 7, "FUT"),
        (269, 31, "USD"),
        (300, 21, "SPX"),
    ]:
        row[offset : offset + width] = text.encode().ljust(width, b"\0")
    row[325] = ord("F")
    row[342] = ord("F")
    row[348] = 7
    row[349] = ord("A")
    row[350] = int(c["month"][4:])
    row[353] = ord("N")
    return bytes(row)


def write_dbn(
    path: Path,
    contracts: list[dict[str, Any]],
    records: list[tuple[int, int, int, int, int, int, int]],
    *,
    definitions: bool = False,
) -> None:
    """Record tuple: provider ID, start ns, raw 1e-9 OHLC integers, volume."""
    raw = metadata(9 if definitions else 6, contracts, 1 if definitions else 2)
    if definitions:
        raw += b"".join(definition(c) for c in contracts)
    else:
        for provider_id, start, op, hi, lo, cl, volume in records:
            c = next(c for c in contracts if c["provider_id"] == provider_id)
            raw += struct.pack(
                "<BBHIQqqqqQ",
                14,
                0x21,
                c["publisher_id"],
                provider_id,
                start,
                op,
                hi,
                lo,
                cl,
                volume,
            )
    path.write_bytes(pa.compress(raw, codec="zstd").to_pybytes())


def write_demo(directory: Path) -> Path:
    """Versioned synthetic November 2022 scenario; no general exchange calendar."""
    directory.mkdir(parents=True, exist_ok=False)
    c = {
        "month": "202212",
        "raw_symbol": "MESZ2",
        "provider_id": 123,
        "publisher_id": 1,
        "activation": "2021-01-01T00:00:00Z",
        "expiration": "2022-12-16T14:30:00Z",
        "currency": "USD",
        "tick": "0.25",
        "multiplier": 5,
        "lot": 1,
        "exchange": "XCME",
    }
    sessions = []
    records = []
    for i in range(9):
        d = date(2022, 11, 21) + timedelta(days=i)
        day = d.isoformat()
        close = None if d.weekday() >= 5 or d.day == 24 else "13:00" if d.day == 25 else "16:00"
        intervals = []
        if d.weekday() < 5:
            previous = (d - timedelta(days=1)).isoformat()
            intervals = [
                [local_ns(previous, "18:00"), local_ns(day, "16:15")],
                [local_ns(day, "16:30"), local_ns(day, "17:00")],
            ]
        sessions.append(
            {
                "day": day,
                "cash_close": close,
                "cme_intervals": [
                    [instant(a).isoformat(), instant(b).isoformat()] for a, b in intervals
                ],
            }
        )
        if close:
            for start in range(local_ns(day, "09:30"), local_ns(day, close), MINUTE):
                records.append(
                    (
                        123,
                        start,
                        5000 * 10**9,
                        5001 * 10**9,
                        4999 * 10**9,
                        5000 * 10**9 + 250_000_000,
                        10,
                    )
                )
    write_dbn(directory / "definitions.dbn.zst", [c], [], definitions=True)
    write_dbn(directory / "bars.dbn.zst", [c], records)
    request_start, request_end = "2022-11-20T00:00:00Z", "2022-11-30T00:00:00Z"
    config = {
        "version": 1,
        "spec": "MES-ITSM-DATA-v1",
        "mode": "offline",
        "synthetic": True,
        "provider": "databento",
        "dataset": "GLBX.MDP3",
        "schema": "ohlcv-1m",
        "delay_seconds": 1,
        "calendar_version": "synthetic-nov2022-v1",
        "roll_version": "monday-v1",
        "rights_ref": "synthetic:generated",
        "start": request_start,
        "end": request_end,
        "study_start": "2022-11-22",
        "study_end": "2022-11-29",
        "contracts": [c],
        "sessions": sessions,
        "rolls": [],
        "chunks": [
            {
                "path": "bars.dbn.zst",
                "definitions": "definitions.dbn.zst",
                "sha256": digest((directory / "bars.dbn.zst").read_bytes()),
                "definitions_sha256": digest((directory / "definitions.dbn.zst").read_bytes()),
                "start": request_start,
                "end": request_end,
            }
        ],
    }
    path = directory / "request.json"
    path.write_bytes(canonical(config))
    return path
