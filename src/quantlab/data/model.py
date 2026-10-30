"""Validated configuration and provider-independent observation types."""

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from functools import cache
from importlib.metadata import version
from importlib.resources import files
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

with files("tzdata.zoneinfo").joinpath("America/New_York").open("rb") as _tz:
    NY = ZoneInfo.from_file(_tz, key="America/New_York")
TZ_VERSION = version("tzdata")
MINUTE = 60_000_000_000
SECOND = 1_000_000_000


class DataError(ValueError):
    """Bounded, non-sensitive input/integrity failure."""


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def timestamp(value: str) -> int:
    try:
        if re.search(r"[.,]\d{7,}", value):
            raise ValueError
        dt = datetime.fromisoformat(value)
        if dt.utcoffset() is None:
            raise ValueError
        delta = dt.astimezone(UTC) - datetime(1970, 1, 1, tzinfo=UTC)
        result = (delta.days * 86400 + delta.seconds) * SECOND + delta.microseconds * 1000
        if not 0 <= result <= 2**63 - 1:
            raise ValueError
        return result
    except (ValueError, TypeError, OverflowError) as exc:
        raise DataError("invalid aware timestamp") from exc


def instant(ns: int) -> datetime:
    return datetime(1970, 1, 1, tzinfo=UTC) + timedelta(microseconds=ns // 1000)


@cache
def local_ns(day: str, clock: str) -> int:
    """New York wall clock to UTC ns; pure and hot (called per candle), hence cached."""
    return timestamp(datetime.fromisoformat(f"{day}T{clock}:00").replace(tzinfo=NY).isoformat())


def fields(value: Any, required: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != required:
        raise DataError("missing or unsupported configuration fields")
    return value


def integer(value: Any, minimum: int = 0, maximum: int = 2**63 - 1) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise DataError("invalid integer field")
    return value


def token(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,96}", value):
        raise DataError("invalid metadata identifier")
    return value


@dataclass(frozen=True)
class Contract:
    month: str
    raw_symbol: str
    provider_id: int
    publisher_id: int
    activation: int
    expiration: int

    @property
    def key(self) -> str:
        return f"CME:MES:{self.month}"

    @property
    def native_id(self) -> str:
        return f"MES-{self.month}.CME"

    @classmethod
    def parse(cls, value: Any) -> "Contract":
        row = fields(
            value,
            {
                "month",
                "raw_symbol",
                "provider_id",
                "publisher_id",
                "activation",
                "expiration",
                "currency",
                "tick",
                "multiplier",
                "lot",
                "exchange",
            },
        )
        month = token(row["month"])
        if not re.fullmatch(r"20\d{2}(03|06|09|12)", month):
            raise DataError("only dated quarterly MES contracts are supported")
        symbol = token(row["raw_symbol"])
        letter = {"03": "H", "06": "M", "09": "U", "12": "Z"}[month[4:]]
        if not re.fullmatch(f"MES{letter}(?:{month[3:4]}|{month[2:4]}|{month[:4]})", symbol):
            raise DataError("symbol and expiry month disagree")
        if (row["currency"], row["tick"], row["multiplier"], row["lot"], row["exchange"]) != (
            "USD",
            "0.25",
            5,
            1,
            "XCME",
        ):
            raise DataError("unsupported MES contract specification")
        integer(row["multiplier"], 5, 5)
        integer(row["lot"], 1, 1)
        activation, expiration = timestamp(row["activation"]), timestamp(row["expiration"])
        if activation >= expiration or instant(expiration).astimezone(NY).strftime("%Y%m") != month:
            raise DataError("invalid activation/expiration")
        return cls(
            month,
            symbol,
            integer(row["provider_id"], 1, 2**32 - 1),
            integer(row["publisher_id"], 1, 65535),
            activation,
            expiration,
        )


@dataclass(frozen=True)
class Session:
    day: str
    cash_close: str | None
    intervals: tuple[tuple[int, int], ...]

    @classmethod
    def parse(cls, value: Any) -> "Session":
        row = fields(value, {"day", "cash_close", "cme_intervals"})
        day = date.fromisoformat(row["day"]).isoformat()
        close = row["cash_close"]
        if close not in (None, "13:00", "16:00"):
            raise DataError("unsupported cash close")
        if date.fromisoformat(day).weekday() >= 5 and close is not None:
            raise DataError("weekend cannot be a cash session")
        intervals = tuple((timestamp(a), timestamp(b)) for a, b in row["cme_intervals"])
        if any(a >= b for a, b in intervals) or any(
            a < prior for (_, prior), (a, _) in zip(intervals, intervals[1:], strict=False)
        ):
            raise DataError("overlapping or reversed CME intervals")
        return cls(day, close, intervals)


@dataclass(frozen=True)
class Chunk:
    path: str
    definitions: str
    sha256: str
    definitions_sha256: str
    start: int
    end: int


@dataclass(frozen=True)
class Config:
    payload: dict[str, Any]
    contracts: tuple[Contract, ...]
    sessions: tuple[Session, ...]
    rolls: tuple[tuple[str, str, str], ...]
    chunks: tuple[Chunk, ...]
    start: int
    end: int
    delay_ns: int

    @classmethod
    def parse(cls, value: Any) -> "Config":
        r = fields(
            value,
            {
                "version",
                "spec",
                "mode",
                "synthetic",
                "provider",
                "dataset",
                "schema",
                "delay_seconds",
                "calendar_version",
                "roll_version",
                "rights_ref",
                "start",
                "end",
                "study_start",
                "study_end",
                "contracts",
                "sessions",
                "rolls",
                "chunks",
            },
        )
        if (
            (r["version"], r["spec"], r["mode"], r["provider"], r["dataset"], r["schema"])
            != (1, "MES-ITSM-DATA-v1", "offline", "databento", "GLBX.MDP3", "ohlcv-1m")
            or type(r["version"]) is not int
            or r["synthetic"] is not True
        ):
            raise DataError("only offline synthetic Databento MES minute inputs are enabled")
        for name in ("calendar_version", "roll_version", "rights_ref"):
            token(r[name])
        if not r["rights_ref"].startswith("synthetic:"):
            raise DataError("synthetic rights reference required; vendor admission is disabled")
        contracts = tuple(Contract.parse(c) for c in r["contracts"])
        if not 1 <= len(contracts) <= 100 or len({c.month for c in contracts}) != len(contracts):
            raise DataError("missing or duplicate contract")
        if len({(c.publisher_id, c.provider_id) for c in contracts}) != len(contracts):
            raise DataError("duplicate source contract ID")
        sessions = tuple(sorted((Session.parse(s) for s in r["sessions"]), key=lambda s: s.day))
        if not 2 <= len(sessions) <= 4000:
            raise DataError("bounded calendar with prior-session context required")
        for a, b in zip(sessions, sessions[1:], strict=False):
            if date.fromisoformat(b.day) - date.fromisoformat(a.day) != timedelta(days=1):
                raise DataError("calendar must explicitly classify every civil date")
        all_intervals = sorted((a, b) for s in sessions for a, b in s.intervals)
        if any(
            a < previous
            for (_, previous), (a, _) in zip(all_intervals, all_intervals[1:], strict=False)
        ):
            raise DataError("overlapping exchange trade dates")
        if not (sessions[0].day < r["study_start"] <= r["study_end"] <= sessions[-1].day):
            raise DataError("study requires explicit prior cash-session context")
        if not any(s.cash_close for s in sessions if s.day < r["study_start"]):
            raise DataError("prior cash session not supplied")
        date.fromisoformat(r["study_start"])
        date.fromisoformat(r["study_end"])
        rolls = []
        chain = sorted(contracts, key=lambda c: c.month)
        for item in r["rolls"]:
            roll = fields(item, {"day", "outgoing", "incoming"})
            d = date.fromisoformat(roll["day"])
            outgoing = next((c for c in contracts if c.month == roll["outgoing"]), None)
            incoming = next((c for c in contracts if c.month == roll["incoming"]), None)
            if (
                outgoing is None
                or incoming is None
                or chain.index(incoming) != chain.index(outgoing) + 1
            ):
                raise DataError("roll must link consecutive supplied quarterly contracts")
            expected_month = int(outgoing.month[4:]) + 3
            expected_year = int(outgoing.month[:4]) + (expected_month > 12)
            if incoming.month != f"{expected_year:04}{(expected_month - 1) % 12 + 1:02}":
                raise DataError("nonconsecutive quarterly roll")
            first = date(int(outgoing.month[:4]), int(outgoing.month[4:]), 1)
            third_friday = first + timedelta(days=(4 - first.weekday()) % 7 + 14)
            monday = third_friday - timedelta(days=4)
            candidates = [
                s.day for s in sessions if s.day >= monday.isoformat() and s.cash_close == "16:00"
            ]
            if (
                not candidates
                or d.isoformat() != candidates[0]
                or outgoing.expiration <= local_ns(d.isoformat(), "09:30")
            ):
                raise DataError("roll must use first full cash session on/after fixed Monday")
            rolls.append((d.isoformat(), outgoing.month, incoming.month))
        rolls.sort()
        if len({d for d, _, _ in rolls}) != len(rolls):
            raise DataError("duplicate roll date")
        start, end = timestamp(r["start"]), timestamp(r["end"])
        if start >= end or not (
            start <= local_ns(r["study_start"], "09:30") < local_ns(r["study_end"], "16:00") <= end
        ):
            raise DataError("empty or reversed request")
        chunks = []
        for item in r["chunks"]:
            c = fields(
                item, {"path", "definitions", "sha256", "definitions_sha256", "start", "end"}
            )
            for name in ("path", "definitions"):
                p = Path(c[name])
                if (
                    p.is_absolute()
                    or ".." in p.parts
                    or not re.fullmatch(r"[A-Za-z0-9_./-]{1,160}", c[name])
                ):
                    raise DataError("only safe relative local paths are accepted")
            for name in ("sha256", "definitions_sha256"):
                if not isinstance(c[name], str) or not re.fullmatch(r"[a-f0-9]{64}", c[name]):
                    raise DataError("source content hash required")
            chunk_start, chunk_end = timestamp(c["start"]), timestamp(c["end"])
            if not start <= chunk_start < chunk_end <= end:
                raise DataError("chunk widens request bounds")
            chunks.append(
                Chunk(
                    c["path"],
                    c["definitions"],
                    c["sha256"],
                    c["definitions_sha256"],
                    chunk_start,
                    chunk_end,
                )
            )
        if not 1 <= len(chunks) <= 100:
            raise DataError("one to 100 local chunks required")
        result = cls(
            json.loads(canonical(r)),
            contracts,
            sessions,
            tuple(rolls),
            tuple(chunks),
            start,
            end,
            integer(r["delay_seconds"], 0, 60) * SECOND,
        )
        for s in sessions:
            if s.cash_close:
                result.selected(s.day)
        return result

    def selected(self, day: str) -> Contract:
        """Selected cash-session contract; not an overnight position rollover API."""
        month = min(c.month for c in self.contracts)
        for roll_day, outgoing, incoming in self.rolls:
            if roll_day <= day:
                if outgoing != month:
                    raise DataError("broken roll chain")
                month = incoming
        contract = next(c for c in self.contracts if c.month == month)
        if not contract.activation <= local_ns(day, "09:30") < contract.expiration:
            raise DataError("selected contract is not active at cash open")
        return contract

    def session_for(self, start: int, end: int) -> Session:
        matches = [s for s in self.sessions if any(a <= start < end <= b for a, b in s.intervals)]
        if len(matches) != 1:
            raise DataError("bar outside supplied CME trading intervals")
        return matches[0]


@dataclass(frozen=True)
class SourceBar:
    contract: Contract
    start: int
    prices: tuple[str, str, str, str]
    volume: int
    source_ref: str


@dataclass(frozen=True)
class Observation:
    contract: str
    start: int
    end: int
    available: int
    open: str
    high: str
    low: str
    close: str
    volume: int
    exchange_trade_date: str
    source_refs: tuple[str, ...]


def same_contract_return(first: Observation, last: Observation, asof_ns: int) -> Decimal:
    if first.contract != last.contract:
        raise DataError("return cannot cross contract boundaries")
    if first.end >= last.end or max(first.available, last.available) > asof_ns:
        raise DataError("return inputs are unordered or unavailable")
    if Decimal(first.close) <= 0 or Decimal(last.close) <= 0:
        raise DataError("return prices must be positive")
    return Decimal(last.close) / Decimal(first.close) - 1
