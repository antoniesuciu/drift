"""Paper-only Alpaca REST execution. No live host, paid feeds or implicit order retries.

Uses the shared durable gate; individual FILL activities own the ledger, never order
average prices. Alpaca paper omits regulatory fees: zero below is a simulation assumption.
"""

import json
import os
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from http.client import HTTPException
from pathlib import Path
from typing import Any, ClassVar
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener
from uuid import UUID

from drift.data.alpaca import Credentials, _NoRedirect, decode, timestamp
from drift.data.model import MINUTE, NY, SECOND, DataError, instant
from drift.execution.model import PaperOrder, PaperPolicy
from drift.execution.paper import PaperGate, Quote, Snapshot
from drift.strategies.calendar import Calendar, SessionSpec
from drift.strategies.market import Candle

PAPER_URL = "https://paper-api.alpaca.markets/v2"
DATA_URL = "https://data.alpaca.markets/v2/stocks"


def ns(value: str) -> int:
    """Alpaca publishes RFC3339 timestamps with up to nine fractional digits."""
    match = re.fullmatch(r"(.+T\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?(Z|[+-]\d{2}:\d{2})", value)
    if not match:
        raise DataError("invalid Alpaca timestamp")
    return int(timestamp(match[1] + match[3]).timestamp()) * SECOND + int(
        (match[2] or "").ljust(9, "0")
    )


def number(value: Any) -> Decimal:
    try:
        result = Decimal(str(value))
    except (ValueError, ArithmeticError):
        raise DataError("invalid broker number") from None
    if not result.is_finite():
        raise DataError("nonfinite broker number")
    return result


def whole(value: Any) -> int:
    result = number(value)
    if result < 0 or result != result.to_integral():
        raise DataError("whole nonnegative shares required")
    return int(result)


@dataclass(frozen=True, slots=True)
class AlpacaPaperConfig(PaperPolicy):
    broker: ClassVar[str] = "alpaca"

    def __post_init__(self) -> None:
        super(AlpacaPaperConfig, self).__post_init__()
        try:
            valid = str(UUID(self.account_id)) == self.account_id
        except ValueError:
            valid = False
        if not valid or self.instrument.symbol != "NVDA" or self.instrument.venue != "XNAS":
            raise DataError("Alpaca pilot requires an explicit paper UUID and NVDA.XNAS")


class AlpacaHTTP:
    """Fixed allow-list; auth headers never enter diagnostics or local output.

    GET can retry once. POST/DELETE are attempted exactly once: uncertain results must
    be reconciled by client_order_id, never repeated. All redirects are forbidden.
    """

    def __init__(
        self,
        credentials: Credentials,
        *,
        authorized: bool,
        max_requests: int = 10000,
        opener: Any = None,
        sleep: Callable[[float], None] = time.sleep,
        receipts: Path | None = None,
    ) -> None:
        if authorized is not True:
            raise DataError("Alpaca paper connection is not authorized")
        if type(max_requests) is not int or not 1 <= max_requests <= 10000:
            raise DataError("invalid request budget")
        self._credentials, self._open = credentials, opener or build_opener(_NoRedirect()).open
        self._sleep = sleep
        self.requests, self.max_requests = 0, max_requests
        self._last = 0.0
        self.receipts = receipts

    def _receipt(self, method: str, path: str, params: Any, raw: bytes) -> None:
        if self.receipts is None:
            return
        self.receipts.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor = os.open(self.receipts, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        with os.fdopen(descriptor, "a") as stream:
            stream.write(
                json.dumps(
                    {
                        "method": method,
                        "path": path,
                        "params": params,
                        "observed_at_ns": time.time_ns(),
                        "body": raw.decode("utf-8"),
                    }
                )
                + "\n"
            )

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
        *,
        data: bool = False,
    ) -> Any:
        allowed = (
            (
                method == "GET"
                and path
                in (
                    "/account",
                    "/clock",
                    "/positions",
                    "/orders",
                    "/calendar",
                    "/assets/NVDA",
                    "/orders:by_client_order_id",
                    "/account/activities",
                )
            )
            or (method == "POST" and path == "/orders")
            or (method == "DELETE" and re.fullmatch(r"/orders/[0-9a-f-]{36}", path))
        )
        if data:
            allowed = method == "GET" and path in ("/NVDA/quotes/latest", "/bars")
            if not params or params.get("feed") != "iex":
                raise DataError("paper market data requires explicit free IEX feed")
        if not allowed:
            raise DataError("route outside paper pilot allow-list")
        url = (DATA_URL if data else PAPER_URL) + path
        if params:
            url += "?" + urlencode(params)
        for attempt in range(2 if method == "GET" else 1):
            if self.requests >= self.max_requests:
                raise DataError("paper request budget exhausted")
            self._sleep(max(0.0, 0.35 - (time.monotonic() - self._last)))
            self.requests += 1
            self._last = time.monotonic()
            request = Request(
                url,
                method=method,
                data=json.dumps(body).encode() if body is not None else None,
                headers={
                    "APCA-API-KEY-ID": self._credentials.key,
                    "APCA-API-SECRET-KEY": self._credentials.secret,
                    "Accept": "application/json",
                    "Accept-Encoding": "identity",
                    "Content-Type": "application/json",
                    "User-Agent": "Drift-paper/0.1",
                },
            )
            status = 0
            try:
                with self._open(request, timeout=10) as response:
                    if response.geturl() != url:
                        raise DataError("Alpaca redirects are forbidden")
                    status = response.status
                    if status in (200, 201, 204):
                        raw = response.read(4 * 1024 * 1024 + 1)
                        if len(raw) > 4 * 1024 * 1024:
                            raise DataError("Alpaca paper response exceeds size limit")
                        result = decode(raw) if raw else None
                        self._receipt(method, path, params, raw)
                        return result
            except HTTPError as exc:
                status = exc.code
                exc.close()
            except (URLError, OSError, TimeoutError, HTTPException):
                if method == "GET" and attempt == 0:
                    self._sleep(1)
                    continue
                raise DataError("Alpaca request failed; outcome may be unknown") from None
            if method == "GET" and attempt == 0 and status in (429, 500, 502, 503, 504):
                self._sleep(2)
                continue
            raise DataError(f"Alpaca HTTP {status}; no paid/feed/host fallback")
        raise DataError("Alpaca read retries exhausted")

    def account(self) -> dict[str, Any]:
        account = self._request("GET", "/account")
        if (
            not isinstance(account, dict)
            or account.get("status") != "ACTIVE"
            or account.get("currency") != "USD"
            or any(
                account.get(k) is not False
                for k in (
                    "account_blocked",
                    "trading_blocked",
                    "trade_suspended_by_user",
                )
            )
        ):
            raise DataError("paper account is unavailable, blocked or not USD")
        return account

    def clock(self) -> dict[str, Any]:
        result = self._request("GET", "/clock")
        if not isinstance(result, dict) or type(result.get("is_open")) is not bool:
            raise DataError("invalid paper clock")
        return result

    def calendar(self, start: str, end: str) -> Calendar:
        rows = self._request("GET", "/calendar", {"start": start, "end": end})
        if not isinstance(rows, list) or any(r.get("open") != "09:30" for r in rows):
            raise DataError("unsupported paper calendar")
        return Calendar(tuple(SessionSpec(r["date"], r["close"]) for r in rows))

    def quote(self) -> Quote:
        raw = self._request("GET", "/NVDA/quotes/latest", {"feed": "iex"}, data=True)
        if not isinstance(raw, dict) or raw.get("symbol") != "NVDA":
            raise DataError("wrong quote symbol")
        q = raw["quote"]
        return Quote(number(q["bp"]), number(q["ap"]), ns(q["t"]), True)

    def candles(self, calendar: Calendar, now: int) -> tuple[Candle, ...]:
        """At most two operational sessions, raw IEX; never a SIP substitute.

        Excludes the forming minute. Availability is when the response was observed,
        so a historical endpoint is never represented as a live receipt in the past.
        """
        sessions = calendar.sessions[-2:]
        if len(sessions) != 2:
            raise DataError("previous trading session is required")
        today = instant(now).astimezone(NY).date().isoformat()
        if sessions[-1].day != today or sessions[0].day < "2026-01-01":
            raise DataError("paper history is restricted to current operational sessions")
        complete = (now - SECOND) // MINUTE * MINUTE
        params = {
            "symbols": "NVDA",
            "timeframe": "1Min",
            "feed": "iex",
            "adjustment": "raw",
            "asof": "-",
            "currency": "USD",
            "sort": "asc",
            "limit": "1000",
            "start": instant(sessions[0].open).isoformat(),
            "end": instant(min(complete, sessions[-1].close) - 1).isoformat(),
        }
        token, seen = "", set()
        bars: dict[int, Candle] = {}
        for _ in range(10):
            if token:
                params["page_token"] = token
            raw = self._request("GET", "/bars", params, data=True)
            observed = time.time_ns()
            if not isinstance(raw, dict) or set(raw.get("bars") or {}) - {"NVDA"}:
                raise DataError("invalid IEX bars response")
            for row in (raw.get("bars") or {}).get("NVDA", []):
                start = ns(row["t"])
                session = calendar.containing(start)
                if session is None or session not in sessions:
                    continue  # Explicitly exclude extended-hours observations.
                if start % MINUTE or start + MINUTE > min(complete, session.close):
                    raise DataError("forming or unaligned paper candle")
                candle = Candle(
                    start,
                    start + MINUTE,
                    max(start + MINUTE + SECOND, observed),
                    number(row["o"]),
                    number(row["h"]),
                    number(row["l"]),
                    number(row["c"]),
                    whole(row["v"]),
                    session.day,
                )
                old = bars.get(start)
                if old is not None and (old.open, old.high, old.low, old.close, old.volume) != (
                    candle.open,
                    candle.high,
                    candle.low,
                    candle.close,
                    candle.volume,
                ):
                    raise DataError("conflicting overlapping IEX candles")
                bars[start] = candle
            next_token = raw.get("next_page_token")
            if next_token is None:
                return tuple(bars[t] for t in sorted(bars))
            if not isinstance(next_token, str) or not next_token or next_token in seen:
                raise DataError("invalid/repeated IEX page token")
            token = next_token
            seen.add(token)
        raise DataError("paper candle pagination budget exhausted")


class AlpacaTransport:
    """A single paper account, one symbol and IOC limits through the shared journal."""

    def __init__(
        self,
        config: AlpacaPaperConfig,
        http: AlpacaHTTP,
        *,
        now: Callable[[], int] = time.time_ns,
    ) -> None:
        if not config.connection_authorized:
            raise DataError("paper connection is not authorized")
        self.config, self.http, self.now = config, http, now
        self.gate: PaperGate | None = None

    def attach(self, gate: PaperGate) -> None:
        if gate.transport is not self or gate.config != self.config:
            raise DataError("paper gate/transport configuration mismatch")
        self.gate = gate

    def managed_accounts(self) -> tuple[str, ...]:
        return (str(self.http.account()["id"]),)

    def _gate(self) -> PaperGate:
        if self.gate is None or not self.config.orders_authorized:
            raise DataError("attached gate and paper-order authorization required")
        return self.gate

    def _order(self, order_id: str) -> dict[str, Any]:
        raw = self.http._request("GET", "/orders:by_client_order_id", {"client_order_id": order_id})
        if self.gate is None or not isinstance(raw, dict):
            raise DataError("missing paper order evidence")
        expected = self.gate._order(order_id)
        if (
            raw.get("client_order_id") != expected.order_id
            or raw.get("symbol") != "NVDA"
            or raw.get("side") != ("buy" if expected.side == 1 else "sell")
            or whole(raw.get("qty")) != expected.quantity
            or raw.get("type") != "limit"
            or raw.get("time_in_force") != "ioc"
            or raw.get("extended_hours") is not False
            or number(raw.get("limit_price")) != expected.limit
        ):
            raise DataError("broker order does not match durable approved intent")
        if str(UUID(raw["id"])) != raw["id"]:
            raise DataError("invalid broker order identity")
        return raw

    def submit(self, order: PaperOrder) -> None:
        gate = self._gate()
        clock = self.http.clock()
        if not clock["is_open"] or not 0 <= self.now() - ns(clock["timestamp"]) <= 5 * SECOND:
            raise DataError("paper market is closed or broker clock is stale")
        gate.native_preflight(order, self.now(), sending=True)
        # No mutation retry, including HTTP errors or lost acknowledgements.
        result = self.http._request(
            "POST",
            "/orders",
            body={
                "symbol": "NVDA",
                "qty": str(order.quantity),
                "side": "buy" if order.side == 1 else "sell",
                "type": "limit",
                "limit_price": str(order.limit),
                "time_in_force": "ioc",
                "extended_hours": False,
                "order_class": "simple",
                "client_order_id": order.order_id,
            },
        )
        if not isinstance(result, dict) or result.get("client_order_id") != order.order_id:
            raise DataError("unconfirmed paper acknowledgement")
        gate.acknowledge(order.order_id)

    def cancel(self, order_id: str) -> None:
        gate = self._gate()
        if self.managed_accounts() != (self.config.account_id,):
            raise DataError("wrong paper account")
        raw = self._order(order_id)
        if raw["status"] in ("filled", "canceled", "expired", "rejected"):
            return  # Status/fill reconciliation still required; no assumed cancellation.
        gate._order(order_id)
        self.http._request("DELETE", "/orders/" + raw["id"])

    def _fills(self, order_id: str, broker_id: str) -> None:
        assert self.gate is not None
        token, seen = "", set()
        for _ in range(20):
            params = {
                "activity_types": "FILL",
                "order_id": broker_id,
                "direction": "asc",
                "page_size": "100",
            }
            if token:
                params["page_token"] = token
            rows = self.http._request("GET", "/account/activities", params)
            if not isinstance(rows, list):
                raise DataError("unknown paper fill history")
            if not rows:
                return
            for row in rows:
                if (
                    row.get("activity_type") != "FILL"
                    or row.get("order_id") != broker_id
                    or row.get("symbol") != "NVDA"
                    or row.get("side")
                    != ("buy" if self.gate._order(order_id).side == 1 else "sell")
                ):
                    raise DataError("fill identity does not match paper order")
                self.gate.record_fill(
                    row["id"],
                    order_id,
                    whole(row["qty"]),
                    number(row["price"]),
                    Decimal(0),
                )
            token = rows[-1]["id"]
            if not isinstance(token, str) or token in seen:
                raise DataError("repeated paper fill page token")
            seen.add(token)
        raise DataError("paper fill pagination budget exhausted")

    def refresh(self, *, resume: bool = False) -> Snapshot:
        if self.gate is None:
            raise DataError("paper gate is not attached")
        gate = self.gate
        gate._ready = False
        try:
            if self.managed_accounts() != (self.config.account_id,):
                raise DataError("wrong paper account")
            open_orders = self.http._request("GET", "/orders", {"status": "open", "limit": "500"})
            if (
                not isinstance(open_orders, list)
                or len(open_orders) >= 500
                or any(o.get("client_order_id") not in gate.orders() for o in open_orders)
            ):
                raise DataError("external or unknown paper orders; isolated account required")
            reports = {}
            for oid in gate.orders():
                raw = self._order(oid)
                self._fills(oid, raw["id"])
                filled = whole(raw["filled_qty"])
                gate.broker_filled(oid, filled)
                if filled != gate._filled(oid):
                    raise DataError("paper fills and order snapshot are inconsistent; retry reads")
                status = raw["status"]
                if status == "filled":
                    reports[oid] = "FILLED"
                elif status in ("canceled", "expired"):
                    reports[oid] = "CANCELLED"
                elif status == "rejected":
                    reports[oid] = "REJECTED"
                elif status in ("new", "accepted", "pending_new", "partially_filled"):
                    reports[oid] = "PARTIAL" if filled else "ACK"
                else:
                    raise DataError("unresolved paper order status")
            positions = self.http._request("GET", "/positions")
            if (
                not isinstance(positions, list)
                or len(positions) > 1
                or any(p.get("symbol") != "NVDA" or p.get("side") != "long" for p in positions)
            ):
                raise DataError("unsupported/external paper position")
            account = self.http.account()
            if account["id"] != self.config.account_id:
                raise DataError("paper account changed during reconciliation")
            snapshot = Snapshot(
                number(account["cash"]),
                whole(positions[0]["qty"]) if positions else 0,
                self.now(),
                max(Decimal(0), number(account["last_equity"]) - number(account["equity"])),
            )
            gate.reconcile(snapshot, reports, self.now(), resume=resume)
            return snapshot
        except Exception:
            gate.halt("alpaca_reconciliation_required")
            raise DataError(
                "Alpaca paper reconciliation failed; inspect private journal/account"
            ) from None


def calendar_window(day: str) -> tuple[str, str]:
    from datetime import timedelta

    current = date.fromisoformat(day)
    return (current - timedelta(days=10)).isoformat(), day
