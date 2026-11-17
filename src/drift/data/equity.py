"""Raw equity minute normalization, calendar coverage and known split evidence.

Minute-specific adaptation of InvestorAI f379dd7 validation principles. No provider calls,
orders, price padding, adjusted executable prices or inference of a calendar from bars.
"""

from dataclasses import asdict, dataclass, replace
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from drift.backtest.data import InstrumentSpec, MarketData
from drift.data.alpaca import Receipt, decode, timestamp
from drift.data.model import SECOND, DataError, canonical, digest, local_ns
from drift.strategies.calendar import MINUTE_NS, Calendar, SessionSpec
from drift.strategies.market import Candle

SPLIT_SOURCE = (
    "https://nvidianews.nvidia.com/news/"
    "nvidia-announces-four-for-one-stock-split-pending-stockholder-approval-at-annual-meeting-set-for-june-3"
)


def iso(ns: int) -> str:
    return datetime.fromtimestamp(ns // SECOND, UTC).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class Split:
    day: str
    ratio: Decimal  # new shares / old shares; previous raw close is divided by this.
    known_at: str
    source: str

    def __post_init__(self) -> None:
        date.fromisoformat(self.day)
        if not self.ratio.is_finite() or self.ratio <= 0 or not self.source:
            raise DataError("invalid split evidence")
        if int(timestamp(self.known_at).timestamp()) * SECOND >= local_ns(self.day, "09:30"):
            raise DataError("split evidence was not available before the effective open")


NVDA_2021_SPLIT = Split("2021-07-20", Decimal(4), "2021-05-22T00:00:00Z", SPLIT_SOURCE)
NVDA_2024_SPLIT = Split(
    "2024-06-10",
    Decimal(10),
    "2024-05-23T00:00:00Z",
    "https://www.sec.gov/Archives/edgar/data/1045810/000104581024000144/nvda-20240607.htm",
)


@dataclass(frozen=True, slots=True)
class PilotRequest:
    start: str = "2021-07-16"
    end: str = "2021-07-21"
    feed: str = "sip"
    delay_seconds: int = 1
    page_size: int = 1000

    def __post_init__(self) -> None:
        a, b = date.fromisoformat(self.start), date.fromisoformat(self.end)
        if not date(2020, 1, 1) <= a <= b <= date(2025, 12, 31) or (b - a).days > 30:
            raise DataError("request must be at most 31 historical dates within 2020–2025")
        if self.feed not in ("sip", "iex"):
            raise DataError("explicit sip or iex feed required")
        if type(self.delay_seconds) is not int or not 1 <= self.delay_seconds <= 60:
            raise DataError("modeled availability delay must be 1 to 60 seconds")
        if type(self.page_size) is not int or not 1 <= self.page_size <= 10000:
            raise DataError("invalid Alpaca page size")

    @property
    def instrument(self) -> InstrumentSpec:
        # Reviewed pilot metadata, not an assertion about all historical equity tick regimes.
        return InstrumentSpec("NVDA", "XNAS", "equity", "USD", Decimal("0.01"), 1, 1, 4)

    def query(self, session: SessionSpec) -> dict[str, str | int]:
        return {
            "symbols": self.instrument.symbol,
            "timeframe": "1Min",
            "feed": self.feed,
            "adjustment": "raw",
            "asof": "-",
            "currency": "USD",
            "sort": "asc",
            "start": iso(session.open),
            "end": iso(session.close - MINUTE_NS),
            "limit": self.page_size,
        }


def calendar_from(request: PilotRequest, receipt: Receipt) -> Calendar:
    rows = decode(receipt.body)
    if not isinstance(rows, list) or not rows or len(rows) > 23:
        raise DataError("monthly calendar needs 1 to 23 explicit sessions")
    try:
        sessions = []
        for r in rows:
            if not request.start <= r["date"] <= request.end or r["open"] != "09:30":
                raise DataError("unexpected calendar date/open")
            sessions.append(SessionSpec(r["date"], r["close"]))
        return Calendar(tuple(sessions))
    except (KeyError, TypeError, ValueError):
        raise DataError("invalid Alpaca calendar") from None


def _number(value: Any, *, integer: bool = False) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, str | int | Decimal):
        raise DataError("provider numbers must preserve decimal precision")
    try:
        result = Decimal(value)
        if not result.is_finite() or result < 0 or (integer and result != result.to_integral()):
            raise ValueError
        return result
    except (ValueError, ArithmeticError):
        raise DataError("invalid provider numeric value") from None


def normalize(
    request: PilotRequest,
    receipts: list[Receipt],
    *,
    source_ref: str | None = None,
) -> tuple[MarketData, dict[str, Any]]:
    """Reconstruct from original receipts, checking query and complete pagination chains."""
    calendars = [r for r in receipts if r.stream == "calendar"]
    assets = [r for r in receipts if r.stream == "asset"]
    if len(calendars) != 1 or len(assets) != 1:
        raise DataError("exactly one asset and calendar receipt required")
    if calendars[0].params != {"start": request.start, "end": request.end, "date_type": "TRADING"}:
        raise DataError("calendar query does not match pilot")
    if assets[0].params != {"symbol": request.instrument.symbol}:
        raise DataError("asset query does not match pilot")
    asset = decode(assets[0].body)
    if (
        not isinstance(asset, dict)
        or asset.get("symbol") != request.instrument.symbol
        or asset.get("class") != "us_equity"
        or asset.get("exchange") != "NASDAQ"
        or not isinstance(asset.get("id"), str)
        or not asset["id"]
    ):
        raise DataError("asset identity/class/venue does not match reviewed equity")
    calendar = calendar_from(request, calendars[0])
    rows: dict[int, Candle] = {}
    row_refs: dict[int, list[str]] = {}
    bar_receipts = [r for r in receipts if r.stream == "bars"]
    used: set[int] = set()
    duplicates, out_of_order = 0, 0
    precision = request.instrument.precision
    for session in calendar.sessions:
        expected = request.query(session)
        pages = [
            (i, r) for i, r in enumerate(bar_receipts) if r.params.get("start") == expected["start"]
        ]
        if not pages:
            raise DataError("missing session request, including empty-session receipts")
        seen: set[str] = set()
        previous = -1
        for index, receipt in pages:
            if receipt.params != expected:
                raise DataError("bar query/pagination chain differs from recorded request")
            used.add(index)
            value = decode(receipt.body)
            if (
                not isinstance(value, dict)
                or "bars" not in value
                or "next_page_token" not in value
                or not isinstance(value["bars"], dict)
                or set(value["bars"]) - {request.instrument.symbol}
            ):
                raise DataError("invalid per-symbol minute bar response")
            bars = value["bars"].get(request.instrument.symbol, [])
            if not isinstance(bars, list):
                raise DataError("expected minute bar array")
            for raw in bars:
                try:
                    moment = timestamp(raw["t"])
                    start = int(moment.timestamp()) * SECOND
                    if (
                        moment.microsecond
                        or start % MINUTE_NS
                        or not session.open <= start < session.close
                    ):
                        raise DataError("bar label is not a requested cash minute start")
                    if start < previous:
                        out_of_order += 1
                    previous = start
                    prices = tuple(_number(raw[k]) for k in ("o", "h", "l", "c"))
                    observed_precision = max(
                        max(0, -int(p.normalize().as_tuple().exponent)) for p in prices
                    )
                    if observed_precision > 9:
                        raise DataError(
                            "bar price exceeds the supported native precision; no rounding"
                        )
                    precision = max(precision, observed_precision)
                    c = Candle(
                        start,
                        start + MINUTE_NS,
                        start + MINUTE_NS + request.delay_seconds * SECOND,
                        prices[0],
                        prices[1],
                        prices[2],
                        prices[3],
                        int(_number(raw["v"], integer=True)),
                        session.day,
                    )
                    if timestamp(receipt.observed_at).timestamp() * SECOND < c.end:
                        raise DataError("receipt predates candle completion")
                    if start in rows:
                        if rows[start] != c:
                            raise DataError("conflicting minute revision; publication rejected")
                        duplicates += 1
                    rows[start] = c
                    row_refs.setdefault(start, []).append(digest(receipt.body))
                except DataError:
                    raise
                except (KeyError, TypeError, ValueError):
                    raise DataError("malformed minute bar") from None
            token = value["next_page_token"]
            if token is None:
                if index != pages[-1][0]:
                    raise DataError("pages follow an exhausted pagination chain")
            else:
                if not isinstance(token, str) or not token or len(token) > 4096 or token in seen:
                    raise DataError("invalid/repeated page token")
                seen.add(token)
                if index == pages[-1][0]:
                    raise DataError("incomplete pagination cannot be published")
                expected = request.query(session) | {"page_token": token}
    if len(used) != len(bar_receipts) or len(calendars) + len(assets) + len(bar_receipts) != len(
        receipts
    ):
        raise DataError("unexpected receipt outside requested sessions/streams")
    candles = tuple(rows[k] for k in sorted(rows))
    data = MarketData.build(
        replace(request.instrument, data_precision=precision),
        calendar,
        candles,
        source_ref=source_ref,
        source_feed=request.feed,
    )
    coverage = []
    for session in calendar.sessions:
        missing = [iso(t) for t in range(session.open, session.close, MINUTE_NS) if t not in rows]
        decision = local_ns(session.day, "15:30")
        coverage.append(
            {
                "day": session.day,
                "expected": (session.close - session.open) // MINUTE_NS,
                "present": sum(c.day == session.day for c in candles),
                "missing_starts": missing,
                "input_minutes_complete": session.full
                and all(t in rows for t in range(session.open, decision, MINUTE_NS)),
                "outcome_close_present": session.close - MINUTE_NS in rows,
            }
        )
    return data, {
        "sessions": coverage,
        "identical_duplicates": duplicates,
        "out_of_order": out_of_order,
        "row_receipts": {str(k): sorted(set(v)) for k, v in row_refs.items()},
        "asset_id_is_current_not_historical": True,
        "feed": request.feed,
        "consolidated": request.feed == "sip",
        "adjustment": "raw",
        "availability": f"modeled minute end + {request.delay_seconds}s; not measured delivery",
        "revision_vintage": "latest historical response; original historical receipt unknown",
    }


def split_evidence(request: PilotRequest) -> list[dict[str, Any]]:
    """Reviewed split-only pilot context; never assert a complete corporate-action history."""
    result = []
    for split in (NVDA_2021_SPLIT, NVDA_2024_SPLIT):
        if request.start <= split.day <= request.end:
            result.append(asdict(split) | {"ratio": str(split.ratio)})
    return result


def identity(request: PilotRequest, receipts: list[Receipt], software: dict[str, Any]) -> str:
    return digest(
        canonical(
            {
                "request": asdict(request),
                "receipts": [r.evidence() for r in receipts],
                "software": software,
                "splits": split_evidence(request),
            }
        )
    )
