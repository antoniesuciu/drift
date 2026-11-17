"""Actual SDK identifiers/events with an offline native-command endpoint; no sockets."""

from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace

import pytest
from ibapi.commission_and_fees_report import CommissionAndFeesReport
from ibapi.contract import Contract
from ibapi.execution import Execution
from nautilus_trader.common.component import TestClock
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.events import OrderFilled
from nautilus_trader.model.identifiers import AccountId, StrategyId, TradeId, TraderId
from nautilus_trader.model.objects import Money, Price
from nautilus_trader.test_kit.stubs.events import TestEventStubs
from test_paper_execution import DAY, NOW, config, proposal, quote, snapshot

from drift.backtest.engine import make_instrument
from drift.data.model import SECOND, DataError
from drift.execution.ibkr import PAPER_CLIENT, node_config
from drift.execution.nautilus import NautilusPaperTransport, PaperEventBridge
from drift.execution.paper import PaperGate
from drift.strategies.calendar import Calendar, SessionSpec


def native_fill(*args, **kwargs):
    event = TestEventStubs.order_filled(*args, **kwargs)
    # The SDK test stub hardcodes TESTER-000; the paper node has its own trader identity.
    raw = OrderFilled.to_dict(event)
    raw["trader_id"] = "DRIFT-001"
    return OrderFilled.from_dict(raw)


class NativeEndpoint:
    def __init__(self):
        self.trader_id, self.id = TraderId("DRIFT-001"), StrategyId("PAPER-001")
        self.clock = TestClock()
        self.clock.set_time(NOW)
        self.sent, self.cancelled, self.orders = [], [], {}
        self.cache = SimpleNamespace(
            order=lambda oid: self.orders.get(str(oid)), positions_open=lambda **kwargs: []
        )

    def submit_order(self, order, *, client_id):
        self.sent.append((order, client_id))
        self.orders[str(order.client_order_id)] = order

    def cancel_order(self, order, *, client_id):
        self.cancelled.append((order, client_id))


def runtime(tmp_path, cfg=None):
    cfg = cfg or config()
    endpoint = NativeEndpoint()
    transport = NautilusPaperTransport(cfg, endpoint)
    ib_client = SimpleNamespace(
        account_id=AccountId(f"{PAPER_CLIENT}-{cfg.account_id}"),
        is_connected=True,
        _client=SimpleNamespace(is_ready=True, accounts=lambda: {cfg.account_id}),
    )
    transport.bind(ib_client)
    gate = PaperGate(cfg, transport, tmp_path / "paper.sqlite", Calendar((SessionSpec(DAY),)))
    transport.attach(gate)
    return gate, transport, endpoint, ib_client, PaperEventBridge(gate, 123)


def ib_receipt(order, *, fee="0.35", price="100.01", contract_id=123, account="DU1234567"):
    execution = Execution()
    execution.execId, execution.acctNumber = "execution-1", account
    execution.shares, execution.price, execution.side = Decimal(order.quantity), float(price), "BOT"
    contract = Contract()
    contract.conId, contract.symbol, contract.secType, contract.currency = (
        contract_id,
        "NVDA",
        "STK",
        "USD",
    )
    commission = CommissionAndFeesReport()
    commission.execId, commission.currency = execution.execId, "USD"
    commission.commissionAndFees = float(fee) if fee is not None else None
    return execution, commission, contract


def test_installed_account_identifier_round_trip_and_builder_key():
    cfg = config()
    assert list(node_config(cfg).exec_clients) == [PAPER_CLIENT]
    account = AccountId(f"{PAPER_CLIENT}-{cfg.account_id}")
    assert str(account.get_issuer()) == PAPER_CLIENT
    assert str(account.get_id()) == cfg.account_id
    assert PAPER_CLIENT.partition("-")[0] == PAPER_CLIENT
    # Installed 1.231 behavior; a documentation example with a hyphenated issuer is unsafe.
    assert AccountId("IB-PAPER-DU1234567").get_id() != cfg.account_id


def test_native_transport_uses_reserved_order_and_explicit_client_route(tmp_path):
    gate, transport, endpoint, _, bridge = runtime(tmp_path)
    gate.reconcile(snapshot(), {}, NOW)
    order = gate.submit(proposal(), quote(), NOW)
    native, client_id = endpoint.sent[0]
    assert str(client_id) == PAPER_CLIENT and str(native.client_order_id) == order.order_id
    with pytest.raises(DataError, match="already been queued"):
        transport.submit(order)
    gate.native_preflight(order, NOW, sending=True)
    assert gate.orders()[order.order_id] == "SENDING"
    with pytest.raises(DataError, match="already sent"):
        gate.native_preflight(order, NOW, sending=True)
    bridge.native_event(
        TestEventStubs.order_accepted(native, account_id=AccountId("IBPAPER-DU1234567"))
    )
    assert gate.orders()[order.order_id] == "ACK"
    gate.kill()
    assert len(endpoint.cancelled) == 1 and str(endpoint.cancelled[0][1]) == PAPER_CLIENT
    gate.close()


def test_actual_native_fill_zero_fee_is_not_accepted_without_raw_evidence(tmp_path):
    gate, _, endpoint, _, bridge = runtime(tmp_path)
    gate.reconcile(snapshot(), {}, NOW)
    order = gate.submit(proposal(), quote(), NOW)
    event = native_fill(
        endpoint.sent[0][0],
        make_instrument(gate.config.instrument),
        account_id=AccountId("IBPAPER-DU1234567"),
        trade_id=TradeId("execution-1"),
        last_px=Price.from_str("100.01"),
        commission=Money(0, USD),
    )
    with pytest.raises(DataError, match="reconciliation"):
        bridge.native_event(event)
    assert gate._filled(order.order_id) == 0  # No fabricated commission or price receipt.
    bridge.ib_execution(order.order_id, *ib_receipt(order))
    bridge.native_event(event)
    assert gate._ledger() == (Decimal("9799.63"), 2)
    gate.close()


@pytest.mark.parametrize("fee", [None, "-1", "1.7976931348623157e308"])
def test_pending_raw_commissions_persist_and_resolve_without_duplicate_shares(tmp_path, fee):
    gate, _, _, _, bridge = runtime(tmp_path)
    gate.reconcile(snapshot(), {}, NOW)
    order = gate.submit(proposal(), quote(), NOW)
    bridge.ib_execution(order.order_id, *ib_receipt(order, fee=fee))
    assert gate._filled(order.order_id) == 2
    with pytest.raises(DataError, match="commission is unconfirmed"):
        gate._ledger()
    gate.close()
    gate, _, _, _, bridge = runtime(tmp_path)
    with pytest.raises(DataError, match="commission is unconfirmed"):
        gate.reconcile(
            snapshot(cash=Decimal("9799.63"), position=2),
            {order.order_id: "FILLED"},
            NOW,
            resume=True,
        )
    bridge.ib_execution(order.order_id, *ib_receipt(order, fee="0.35"))
    gate.reconcile(
        snapshot(cash=Decimal("9799.63"), position=2), {order.order_id: "FILLED"}, NOW, resume=True
    )
    assert gate._filled(order.order_id) == 2
    assert gate._ledger() == (Decimal("9799.63"), 2)
    gate.close()


def test_unrounded_raw_execution_owns_cash_instead_of_native_price_rounding(tmp_path):
    gate, _, endpoint, _, bridge = runtime(tmp_path)
    gate.reconcile(snapshot(), {}, NOW)
    order = gate.submit(proposal(), quote(), NOW)
    bridge.ib_execution(order.order_id, *ib_receipt(order, price="100.005"))
    native = native_fill(
        endpoint.sent[0][0],
        make_instrument(gate.config.instrument),
        account_id=AccountId("IBPAPER-DU1234567"),
        trade_id=TradeId("execution-1"),
        last_px=Price.from_str("100.01"),
        commission=Money(Decimal("0.35"), USD),
    )
    bridge.native_event(native)
    assert gate._ledger() == (Decimal("9799.640"), 2)
    gate.close()


@pytest.mark.parametrize("changes", [{"contract_id": 999}, {"account": "U9999999"}])
def test_raw_execution_account_contract_mismatches_halt(tmp_path, changes):
    gate, _, _, _, bridge = runtime(tmp_path)
    gate.reconcile(snapshot(), {}, NOW)
    order = gate.submit(proposal(), quote(), NOW)
    with pytest.raises(DataError, match="diagnostics withheld"):
        bridge.ib_execution(order.order_id, *ib_receipt(order, **changes))
    assert gate._filled(order.order_id) == 0
    with pytest.raises(DataError, match="halted"):
        gate.submit(proposal(NOW + SECOND), quote(NOW + SECOND), NOW + SECOND)
    gate.close()


def test_native_wire_preflight_rejects_expired_changed_or_disconnected_approval(tmp_path):
    gate, _, _, client, bridge = runtime(tmp_path)
    gate.reconcile(snapshot(), {}, NOW)
    order = gate.submit(proposal(), quote(), NOW)
    for candidate, at in ((order, order.valid_until), (replace(order, quantity=100), NOW)):
        with pytest.raises(DataError):
            gate.native_preflight(candidate, at, sending=True)
    client._client.is_ready = False
    with pytest.raises(DataError, match="verification failed"):
        gate.native_preflight(order, NOW, sending=True)
    assert gate.orders()[order.order_id] == "SUBMITTED"
    bridge.disconnected()
    assert gate._meta("halt") == "broker_disconnected"
    gate.close()


def test_cancel_status_fill_hint_blocks_stale_flat_snapshot_until_execution_arrives(tmp_path):
    gate, _, _, _, bridge = runtime(tmp_path)
    gate.reconcile(snapshot(), {}, NOW)
    order = gate.submit(proposal(), quote(), NOW)
    bridge.ib_status(order.order_id, "Cancelled", 1, 1, "DU1234567")
    assert gate.orders()[order.order_id] == "CANCELLED"
    with pytest.raises(DataError, match="awaiting complete execution"):
        gate.reconcile(snapshot(), {order.order_id: "CANCELLED"}, NOW)
    fill, fee, contract = ib_receipt(order)
    fill.shares = Decimal(1)
    bridge.ib_execution(order.order_id, fill, fee, contract)
    gate.reconcile(
        snapshot(cash=Decimal("9899.64"), position=1), {order.order_id: "CANCELLED"}, NOW
    )
    assert gate.orders()[order.order_id] == "CANCELLED"
    gate.close()


def test_native_cache_mismatch_after_restart_blocks_new_wire_risk(tmp_path):
    gate, transport, _, _, bridge = runtime(tmp_path)
    gate.reconcile(snapshot(), {}, NOW)
    order = gate.submit(proposal(), quote(), NOW)
    bridge.ib_execution(order.order_id, *ib_receipt(order))
    gate.reconcile(snapshot(cash=Decimal("9799.63"), position=2), {order.order_id: "FILLED"}, NOW)
    with pytest.raises(DataError, match="native position differs"):
        transport.verify_native_position()
    assert gate._meta("halt") == "native_position_mismatch"
    gate.close()
