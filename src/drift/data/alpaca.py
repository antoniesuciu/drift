"""Bounded, GET-only historical transport adapted from InvestorAI f379dd7.

No trading routes, automatic credential discovery, paid/recent feed or feed fallback.
Pagination/retry/receipt design follows its alpaca.py, alpaca_replay.py and alpaca_source.py;
this module is independent of InvestorAI and adds minute/development-window constraints.
"""

import json
import math
import re
import shlex
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from email.utils import parsedate_to_datetime
from http.client import HTTPException
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from drift.data.model import DataError, digest

SAFE_HEADERS = {
    "content-type",
    "x-request-id",
    "x-ratelimit-limit",
    "x-ratelimit-remaining",
    "x-ratelimit-reset",
    "retry-after",
}
ENDPOINTS = {
    "bars": "https://data.alpaca.markets/v2/stocks/bars",
    "calendar": "https://paper-api.alpaca.markets/v2/calendar",
}
KEY_NAMES = ("ALPACA_API_KEY_ID", "APCA_API_KEY_ID", "ALPACA_API_KEY")
SECRET_NAMES = ("ALPACA_SECRET_KEY", "APCA_API_SECRET_KEY", "ALPACA_API_SECRET")


def timestamp(value: str) -> datetime:
    try:
        if re.search(r"\.\d{7}", value):
            raise ValueError
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None:
            raise ValueError
        return result.astimezone(UTC)
    except (ValueError, TypeError, AttributeError):
        raise DataError("expected an aware RFC3339 timestamp") from None


def decode(body: bytes) -> Any:
    def invalid(value: str) -> None:
        raise DataError("nonfinite provider JSON")

    try:
        return json.loads(body, parse_float=Decimal, parse_constant=invalid)
    except (ValueError, UnicodeError, RecursionError):
        raise DataError("invalid provider JSON") from None


@dataclass(frozen=True)
class Credentials:
    key: str = field(repr=False)
    secret: str = field(repr=False)

    def __post_init__(self) -> None:
        if any(not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", v) for v in (self.key, self.secret)):
            raise DataError("invalid Alpaca credentials; values withheld")

    @classmethod
    def read(cls, path: Path) -> "Credentials":
        """Read only an explicitly supplied dotenv file, without shell evaluation."""
        try:
            if path.stat().st_size > 65536:
                raise ValueError
            values: dict[str, str] = {}
            for line in path.read_text().splitlines():
                match = re.match(r"\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)", line)
                if match and match[1] in (*KEY_NAMES, *SECRET_NAMES, "ALPACA_PAPER"):
                    parts = shlex.split(match[2], comments=True)
                    if len(parts) != 1 or match[1] in values:
                        raise ValueError
                    values[match[1]] = parts[0]
            if values.get("ALPACA_PAPER", "true").lower() not in ("true", "yes", "1"):
                raise ValueError

            def unique(names: tuple[str, ...]) -> str:
                found = {values[n] for n in names if n in values}
                if len(found) != 1:
                    raise ValueError
                return found.pop()

            return cls(unique(KEY_NAMES), unique(SECRET_NAMES))
        except (OSError, UnicodeError, ValueError):
            raise DataError("missing/invalid Alpaca paper credentials; values withheld") from None


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


@dataclass(frozen=True)
class Receipt:
    stream: str
    params: dict[str, str | int]
    body: bytes = field(repr=False)
    observed_at: str
    headers: dict[str, str]
    endpoint: str

    def evidence(self) -> dict[str, Any]:
        return {
            "stream": self.stream,
            "params": dict(self.params),
            "sha256": digest(self.body),
            "observed_at": self.observed_at,
            "headers": dict(self.headers),
            "endpoint": self.endpoint,
        }


class AlpacaClient:
    """One invocation's request/retry/pacing budget. It cannot submit any order."""

    def __init__(
        self,
        credentials: Credentials,
        *,
        max_requests: int = 40,
        retries: int = 2,
        timeout: float = 10,
        deadline: float = 120,
        opener: Any = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if (
            type(max_requests) is not int
            or not 1 <= max_requests <= 100
            or type(retries) is not int
            or not 0 <= retries <= 2
            or not math.isfinite(timeout)
            or not 0 < timeout <= 30
            or not math.isfinite(deadline)
            or not 0 < deadline <= 300
        ):
            raise DataError("invalid bounded Alpaca policy")
        self._credentials = credentials
        self._open = opener or build_opener(_NoRedirect()).open
        self.clock, self.sleep, self.now = clock, sleep, now
        self.max_requests, self.retries, self.timeout = max_requests, retries, timeout
        self._end = clock() + deadline
        self._last: float | None = None
        self._cooldown = 0.0
        self.requests: list[dict[str, Any]] = []

    def _wait(self, delay: float) -> None:
        if not math.isfinite(delay) or not 0 <= delay <= 60 or self.clock() + delay >= self._end:
            raise DataError("Alpaca cooldown/deadline budget exhausted")
        if delay:
            self.sleep(delay)

    def get(self, stream: str, params: dict[str, str | int]) -> Receipt:
        params = dict(params)
        allowed = {
            "bars": {
                "symbols",
                "timeframe",
                "start",
                "end",
                "feed",
                "adjustment",
                "limit",
                "asof",
                "currency",
                "sort",
                "page_token",
            },
            "calendar": {"start", "end", "date_type"},
            "asset": {"symbol"},
        }
        if stream not in allowed or set(params) - allowed[stream]:
            raise DataError("unsupported read-only historical route/query")
        credentials = self._credentials
        if any(s in str(v) for s in (credentials.key, credentials.secret) for v in params.values()):
            raise DataError("credentials forbidden in query/provenance")
        if stream == "asset":
            symbol = str(params.get("symbol", ""))
            if not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,19}", symbol):
                raise DataError("invalid asset symbol")
            endpoint = "https://paper-api.alpaca.markets/v2/assets/" + symbol
            query: dict[str, str | int] = {}
        else:
            endpoint, query = ENDPOINTS[stream], params
        if stream == "bars":
            start, end = timestamp(str(params.get("start"))), timestamp(str(params.get("end")))
            if (
                params.get("timeframe") != "1Min"
                or params.get("adjustment") != "raw"
                or params.get("feed") not in ("sip", "iex")
                or params.get("asof") != "-"
                or params.get("currency") != "USD"
                or params.get("sort") != "asc"
                or not start <= end
                or start.year < 2020
                or end.year > 2025
                or end - start > timedelta(days=1)
                or end > self.now() - timedelta(minutes=15)
            ):
                raise DataError("only raw 2020–2025 historical minute bars are enabled")
        url = endpoint + ("?" + urlencode(query) if query else "")
        for attempt in range(self.retries + 1):
            if len(self.requests) >= self.max_requests:
                raise DataError("Alpaca request budget exhausted")
            self._wait(self._cooldown)
            self._cooldown = 0
            if self._last is not None:
                self._wait(max(0, 0.5 - (self.clock() - self._last)))
            self._wait(0)
            self._last = self.clock()
            request = Request(
                url,
                method="GET",
                headers={
                    "APCA-API-KEY-ID": credentials.key,
                    "APCA-API-SECRET-KEY": credentials.secret,
                    "Accept": "application/json",
                    "Accept-Encoding": "identity",
                    "User-Agent": "Drift/0.1 private research",
                },
            )
            self.requests.append({"stream": stream, "params": dict(params), "status": None})
            status, headers, body = 0, {}, b""
            try:
                with self._open(
                    request, timeout=min(self.timeout, self._end - self.clock())
                ) as res:
                    if res.geturl() != url:
                        raise DataError("Alpaca redirects are forbidden")
                    status = res.status
                    headers = {
                        str(k).lower(): str(v)
                        for k, v in res.headers.items()
                        if str(k).lower() in SAFE_HEADERS
                    }
                    if status == 200:
                        body = res.read(16 * 1024 * 1024 + 1)
                        if len(body) > 16 * 1024 * 1024:
                            raise DataError("Alpaca response exceeds 16 MiB")
            except HTTPError as exc:
                status = exc.code
                headers = {
                    str(k).lower(): str(v)
                    for k, v in exc.headers.items()
                    if str(k).lower() in SAFE_HEADERS
                }
                exc.close()  # Do not read potentially sensitive error bodies.
            except (URLError, TimeoutError, OSError, HTTPException):
                if attempt == self.retries:
                    raise DataError("Alpaca network failure; diagnostics withheld") from None
                self._wait(float(2**attempt))
                continue
            self.requests[-1]["status"] = status
            self._wait(0)
            now = self.now()
            quota = 0.0
            if headers.get("x-ratelimit-remaining") == "0" or (
                status == 429 and "x-ratelimit-reset" in headers
            ):
                try:
                    reset = float(headers["x-ratelimit-reset"])
                    if not math.isfinite(reset) or reset < 0:
                        raise ValueError
                    quota = max(0, reset - now.timestamp())
                except (KeyError, ValueError):
                    raise DataError("invalid Alpaca quota reset") from None
            if status == 200:
                if any(
                    s.encode() in body or any(s in v for v in headers.values())
                    for s in (credentials.key, credentials.secret)
                ):
                    raise DataError("authentication echoed in response; evidence withheld")
                decode(body)
                self._cooldown = quota
                return Receipt(stream, params, body, now.isoformat(), headers, endpoint)
            if status not in (429, 500, 502, 503, 504) or attempt == self.retries:
                raise DataError(f"Alpaca HTTP {status}; no feed/authentication/paid fallback")
            delay = max(float(2**attempt), quota)
            if "retry-after" in headers:
                try:
                    try:
                        requested = float(headers["retry-after"])
                    except ValueError:
                        requested = (
                            parsedate_to_datetime(headers["retry-after"]) - now
                        ).total_seconds()
                    if not math.isfinite(requested) or requested < 0:
                        raise ValueError
                    delay = max(delay, requested)
                except (ValueError, TypeError, OverflowError):
                    raise DataError("invalid Alpaca Retry-After") from None
            self._wait(delay)
        raise AssertionError("unreachable")

    def pages(
        self,
        params: dict[str, str | int],
        *,
        on_receipt: Callable[[Receipt], None] | None = None,
    ) -> list[Receipt]:
        """A short/empty page is not exhaustion. Only an explicit null token is."""
        result: list[Receipt] = []
        seen: set[str] = set()
        while True:
            receipt = self.get("bars", params)
            if on_receipt is not None:
                on_receipt(receipt)
            page = decode(receipt.body)
            if not isinstance(page, dict) or "bars" not in page or "next_page_token" not in page:
                raise DataError("missing provider payload/pagination state")
            result.append(receipt)
            token = page["next_page_token"]
            if token is None:
                return result
            if not isinstance(token, str) or not token or len(token) > 4096 or token in seen:
                raise DataError("invalid/repeated Alpaca page token")
            seen.add(token)
            params = params | {"page_token": token}
