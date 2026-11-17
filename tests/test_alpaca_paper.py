"""Real REST shapes with a recording opener; sockets/credentials are never used."""

import json
from dataclasses import replace
from decimal import Decimal
from io import BytesIO
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit

import pytest

from drift.backtest.risk import RiskLimits, Sizing
from drift.data.alpaca import Credentials
from drift.data.equity import PilotRequest
from drift.data.model import SECOND, DataError, instant, local_ns
from drift.execution.alpaca import (
    DATA_URL,
    PAPER_URL,
    AlpacaHTTP,
    AlpacaPaperConfig,
    AlpacaTransport,
    ns,
)
from drift.execution.alpaca_cli import PaperSession, configuration
from drift.execution.paper import PaperGate
from drift.strategies.calendar import Calendar, SessionSpec
from drift.strategies.market import Candle
from drift.strategies.proposal import Intent, new_proposal

ACCOUNT = "00000000-0000-4000-8000-000000000001"
BROKER_ID = "00000000-0000-4000-8000-000000000002"
DAY = "2026-10-30"
NOW = local_ns(DAY, "15:30") + 2 * SECOND
CALENDAR = Calendar((SessionSpec("2026-10-29"), SessionSpec(DAY)))


def config(**changes):
    return replace(
        AlpacaPaperConfig(
            ACCOUNT,
            PilotRequest().instrument,
            RiskLimits(Decimal(2), Decimal(1000), Decimal(1), 1, Decimal(10), 30),
            Sizing("fixed_quantity", Decimal(2)),
            Decimal(1000),
            10,
            30,
            connection_authorized=True,
            orders_authorized=True,
        ),
        **changes,
    )


def proposal(now=NOW, intent=Intent.LONG):
    return new_proposal(
        agent_id="paper-test",
        strategy_id="PAPER-ITSM-IEX-001",
        instrument_id="NVDA.XNAS",
        version="test-v1",
        generated_at=now,
        valid_seconds=30,
        horizon_seconds=60,
        intent=intent,
        rationale="synthetic",
        reasons=(),
        refs=("alpaca:iex:synthetic",),
    )


class Response(BytesIO):
    def __init__(self, request, data, status=200):
        super().__init__(json.dumps(data).encode())
        self.url, self.status = request.full_url, status

    def geturl(self):
        return self.url


class Broker:
    def __init__(self):
        self.requests, self.orders, self.fills = [], {}, []
        self.cash, self.position, self.market_open = Decimal(10000), 0, True
        self.post_error, self.wrong_account, self.external_order = False, False, False
        self.now = NOW

    def open(self, request, **kwargs):
        self.requests.append(request)
        path = urlsplit(request.full_url).path.removeprefix("/v2")
        query = parse_qs(urlsplit(request.full_url).query)
        if request.method == "POST":
            order = json.loads(request.data)
            self.orders[order["client_order_id"]] = order | {
                "id": f"00000000-0000-4000-8000-{len(self.orders) + 2:012d}",
                "status": "new",
                "filled_qty": "0",
            }
            if self.post_error:
                raise URLError("sensitive credential diagnostic")
            result = self.orders[order["client_order_id"]]
        elif request.method == "DELETE":
            result = None
        elif path == "/account":
            result = {
                "id": ACCOUNT if not self.wrong_account else BROKER_ID,
                "status": "ACTIVE",
                "currency": "USD",
                "trading_blocked": False,
                "account_blocked": False,
                "trade_suspended_by_user": False,
                "cash": str(self.cash),
                "equity": str(self.cash + self.position * 100),
                "last_equity": "10000",
            }
        elif path == "/clock":
            result = {"is_open": self.market_open, "timestamp": instant(self.now).isoformat()}
        elif path == "/positions":
            result = [{"symbol": "NVDA", "qty": str(self.position), "side": "long"}]
            if not self.position:
                result = []
        elif path == "/orders":
            result = [o for o in self.orders.values() if o["status"] in ("new", "partially_filled")]
            if self.external_order:
                result.append({"client_order_id": "somebody-else"})
        elif path == "/orders:by_client_order_id":
            result = self.orders[query["client_order_id"][0]]
        elif path == "/account/activities":
            result = (
                []
                if "page_token" in query
                else [f for f in self.fills if f["order_id"] == query["order_id"][0]]
            )
        elif path == "/stocks/NVDA/quotes/latest":
            result = {
                "symbol": "NVDA",
                "quote": {"bp": 100, "ap": 100.01, "t": instant(self.now).isoformat()},
            }
        elif path == "/calendar":
            result = [
                {"date": s.day, "open": "09:30", "close": s.cash_close} for s in CALENDAR.sessions
            ]
        elif path == "/stocks/bars":
            result = {"bars": {"NVDA": []}, "next_page_token": None}
        else:
            raise AssertionError(path)
        return Response(request, result)

    def fill(self, oid, quantity, price="100.00", *, terminal="filled"):
        order = self.orders[oid]
        side = 1 if order["side"] == "buy" else -1
        self.position += side * quantity
        self.cash -= side * quantity * Decimal(price)
        order["filled_qty"] = str(int(order["filled_qty"]) + quantity)
        order["status"] = terminal
        self.fills.append(
            {
                "id": f"20261030::{len(self.fills)}",
                "order_id": order["id"],
                "activity_type": "FILL",
                "symbol": "NVDA",
                "side": order["side"],
                "qty": str(quantity),
                "price": price,
            }
        )


def setup(tmp_path, **changes):
    broker = Broker()
    http = AlpacaHTTP(
        Credentials("synthetic-key", "synthetic-secret"),
        authorized=True,
        opener=broker.open,
        sleep=lambda _: None,
    )
    transport = AlpacaTransport(config(**changes), http, now=lambda: broker.now)
    gate = PaperGate(transport.config, transport, tmp_path / "paper.sqlite", CALENDAR)
    transport.attach(gate)
    return broker, http, transport, gate


def test_paper_endpoint_limit_ioc_and_individual_fill_reconciliation(tmp_path):
    broker, http, transport, gate = setup(tmp_path)
    try:
        snapshot = transport.refresh()
        assert snapshot.position == 0 and snapshot.loss_today == 0
        order = gate.submit(proposal(), http.quote(), NOW)
        post = [r for r in broker.requests if r.method == "POST"]
        assert len(post) == 1 and post[0].full_url == PAPER_URL + "/orders"
        body = json.loads(post[0].data)
        assert body["qty"] == "2" and body["limit_price"] == "100.01"
        assert body["time_in_force"] == "ioc" and body["extended_hours"] is False
        assert gate.orders()[order.order_id] == "ACK"
        broker.fill(order.order_id, 1, terminal="partially_filled")
        assert transport.refresh().position == 1
        broker.fill(order.order_id, 1)
        assert transport.refresh().position == 2
        assert transport.refresh().position == 2  # Duplicate receipts do not duplicate shares.
        assert gate._ledger() == (Decimal(9800), 2)
        assert gate.orders()[order.order_id] == "FILLED"
        assert all(r.full_url.startswith((PAPER_URL, DATA_URL)) for r in broker.requests)
    finally:
        gate.close()


def test_uncertain_post_is_not_repeated_and_reconciles_by_client_id(tmp_path):
    broker, http, transport, gate = setup(tmp_path)
    try:
        transport.refresh()
        broker.post_error = True
        with pytest.raises(DataError, match="outcome unknown"):
            gate.submit(proposal(), http.quote(), NOW)
        oid = next(iter(gate.orders()))
        assert gate.orders()[oid] == "UNKNOWN"
        transport.refresh(resume=True)
        assert gate.orders()[oid] == "ACK"
        with pytest.raises(DataError, match="duplicate"):
            gate.submit(proposal(), http.quote(), NOW)
        assert len([r for r in broker.requests if r.method == "POST"]) == 1
    finally:
        gate.close()


@pytest.mark.parametrize("case", ["closed", "wrong_account", "external", "missing_fills"])
def test_closed_market_and_uncertain_state_halt_without_new_orders(tmp_path, case):
    broker, http, transport, gate = setup(tmp_path)
    try:
        transport.refresh()
        if case == "closed":
            broker.market_open = False
            with pytest.raises(DataError):
                gate.submit(proposal(), http.quote(), NOW)
        elif case == "missing_fills":
            order = gate.submit(proposal(), http.quote(), NOW)
            broker.fill(order.order_id, 2)
            broker.fills.clear()
            with pytest.raises(DataError, match="reconciliation failed"):
                transport.refresh()
        else:
            broker.wrong_account = case == "wrong_account"
            broker.external_order = case == "external"
            with pytest.raises(DataError, match="reconciliation failed"):
                transport.refresh()
        count = len([r for r in broker.requests if r.method == "POST"])
        assert count == (1 if case == "missing_fills" else 0)
    finally:
        gate.close()


def test_no_gate_no_authorization_or_modified_intent_cannot_send(tmp_path):
    broker, http, transport, gate = setup(tmp_path, orders_authorized=False)
    try:
        transport.refresh()
        with pytest.raises(DataError, match="not authorized"):
            gate.submit(proposal(), http.quote(), NOW)
        assert not any(r.method == "POST" for r in broker.requests)
    finally:
        gate.close()
    with pytest.raises(DataError, match="not authorized"):
        AlpacaHTTP(Credentials("synthetic-key", "synthetic-secret"), authorized=False)
    with pytest.raises(DataError, match="UUID"):
        config(account_id="DU1234567")


def test_cancel_requires_owned_matching_order_and_does_not_infer_terminal(tmp_path):
    broker, http, transport, gate = setup(tmp_path)
    try:
        transport.refresh()
        order = gate.submit(proposal(), http.quote(), NOW)
        broker.orders[order.order_id]["qty"] = "3"
        with pytest.raises(DataError):
            transport.cancel(order.order_id)
        assert not any(r.method == "DELETE" for r in broker.requests)
        broker.orders[order.order_id]["qty"] = "2"
        gate.kill()
        assert [r.full_url for r in broker.requests if r.method == "DELETE"] == [
            PAPER_URL + "/orders/" + BROKER_ID,
        ]
        assert gate.orders()[order.order_id] == "CANCEL_REQUESTED"
    finally:
        gate.close()


@pytest.mark.parametrize("method", ["POST", "DELETE", "GET"])
def test_http_error_redaction_and_mutation_retry_policy(method):
    calls = []

    def failing(request, **kwargs):
        calls.append(request)
        raise HTTPError(
            request.full_url, 429, "sensitive diagnostic", {}, BytesIO(b"synthetic-secret")
        )

    http = AlpacaHTTP(
        Credentials("synthetic-key", "synthetic-secret"),
        authorized=True,
        opener=failing,
        sleep=lambda _: None,
    )
    path = "/orders/" + BROKER_ID if method == "DELETE" else "/orders"
    with pytest.raises(DataError, match="HTTP 429") as caught:
        http._request(method, path)
    assert "secret" not in str(caught.value) and "sensitive" not in str(caught.value)
    assert len(calls) == (2 if method == "GET" else 1)


def test_redirect_paid_feed_and_arbitrary_route_denied():
    def redirect(request, **kwargs):
        result = Response(request, {})
        result.url = "https://api.alpaca.markets/v2/account"
        return result

    http = AlpacaHTTP(
        Credentials("synthetic-key", "synthetic-secret"),
        authorized=True,
        opener=redirect,
        sleep=lambda _: None,
    )
    with pytest.raises(DataError, match="redirects"):
        http.account()
    with pytest.raises(DataError, match="allow-list"):
        http._request("POST", "/account/reset")
    with pytest.raises(DataError, match="IEX"):
        http._request("GET", "/bars", {"feed": "sip"}, data=True)


def test_nanosecond_quote_clock_and_private_account_binding(tmp_path):
    assert ns("2026-10-30T19:30:02.123456789Z") == NOW + 123456789
    with pytest.raises(DataError):
        ns("2026-10-30T19:30:02.1234567890Z")
    path = tmp_path / "config.json"
    cfg = configuration(path, ACCOUNT, orders=False)
    assert cfg.sizing.amount == 1 and not cfg.orders_authorized
    assert path.stat().st_mode & 0o777 == 0o600
    assert ACCOUNT not in repr(cfg)
    with pytest.raises(DataError, match="bound account"):
        configuration(path, BROKER_ID, orders=False)


def test_session_uses_existing_itsm_and_never_trades_when_late(tmp_path):
    broker, http, transport, gate = setup(tmp_path)
    try:
        snapshot = transport.refresh()
        session = PaperSession(http, transport, gate, CALENDAR, tmp_path / "events.jsonl")
        assert not session.tick(NOW + 40 * SECOND, snapshot)
        assert "missed_decision" in (tmp_path / "events.jsonl").read_text()
        assert not any(r.method == "POST" for r in broker.requests)
    finally:
        gate.close()


def test_candles_keep_explicit_iex_and_do_not_read_holdout(tmp_path):
    broker, http, transport, gate = setup(tmp_path)
    try:
        assert http.candles(CALENDAR, NOW) == ()
        request = broker.requests[-1]
        params = parse_qs(urlsplit(request.full_url).query)
        assert params["feed"] == ["iex"] and params["adjustment"] == ["raw"]
        assert "2026-10-29" in params["start"][0]
        assert ns(params["end"][0]) < local_ns(DAY, "15:30")
        with pytest.raises(DataError, match="operational"):
            http.candles(CALENDAR, NOW - 24 * 3600 * SECOND)
    finally:
        gate.close()


def test_session_entry_fill_timed_exit_and_flat_reconciliation(tmp_path, monkeypatch):
    broker, http, transport, gate = setup(tmp_path)
    monkeypatch.setattr("time.time_ns", lambda: broker.now)
    candles = []
    for session in CALENDAR.sessions:
        end = session.close if session.day != DAY else local_ns(DAY, "15:30")
        for start in range(session.open, end, 60 * SECOND):
            price = Decimal(100)
            if session.day == DAY:
                price = Decimal(102) if start < local_ns(DAY, "15:00") else Decimal(104)
            candles.append(
                Candle(
                    start, start + 60 * SECOND, NOW, price, price, price, price, 100, session.day
                )
            )
    monkeypatch.setattr(http, "candles", lambda *_: tuple(candles))
    try:
        session = PaperSession(http, transport, gate, CALENDAR, tmp_path / "events.jsonl")
        assert not session.tick(NOW, transport.refresh())
        entry = next(iter(gate.orders()))
        broker.fill(entry, 2)
        assert transport.refresh().position == 2
        assert not session.tick(NOW, transport.refresh())
        broker.now = local_ns(DAY, "15:58")
        assert not session.tick(broker.now, transport.refresh())
        exit_id = [oid for oid in gate.orders() if oid != entry][0]
        broker.fill(exit_id, 2)
        assert session.tick(broker.now, transport.refresh())
        assert gate._ledger() == (Decimal(10000), 0)
        assert len([r for r in broker.requests if r.method == "POST"]) == 2
    finally:
        gate.close()


def test_bar_pages_completion_and_private_receipts(tmp_path):
    requests = []
    row = {"t": "2026-10-30T19:29:00Z", "o": 100, "h": 101, "l": 99, "c": 100.5, "v": 20}

    def pages(request, **kwargs):
        requests.append(request)
        query = parse_qs(urlsplit(request.full_url).query)
        page = {
            "bars": {"NVDA": [row]},
            "next_page_token": None if "page_token" in query else "second",
        }
        return Response(request, page)

    http = AlpacaHTTP(
        Credentials("synthetic-key", "synthetic-secret"),
        authorized=True,
        opener=pages,
        sleep=lambda _: None,
        receipts=tmp_path / "receipts.jsonl",
    )
    candles = http.candles(CALENDAR, NOW)
    assert len(requests) == 2 and len(candles) == 1
    assert candles[0].end == local_ns(DAY, "15:30")
    assert candles[0].close == Decimal("100.5")
    receipt = (tmp_path / "receipts.jsonl").read_text()
    assert "synthetic-secret" not in receipt and "synthetic-key" not in receipt
    assert '"feed": "iex"' in receipt
    assert (tmp_path / "receipts.jsonl").stat().st_mode & 0o777 == 0o600
    row["t"] = "2026-10-30T19:30:00Z"
    with pytest.raises(DataError, match="forming"):
        http.candles(CALENDAR, NOW)


def test_repeated_bar_page_token_is_rejected():
    def repeated(request, **kwargs):
        return Response(request, {"bars": {"NVDA": []}, "next_page_token": "same"})

    http = AlpacaHTTP(
        Credentials("synthetic-key", "synthetic-secret"),
        authorized=True,
        opener=repeated,
        sleep=lambda _: None,
    )
    with pytest.raises(DataError, match="repeated"):
        http.candles(CALENDAR, NOW)
