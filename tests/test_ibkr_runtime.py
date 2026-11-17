"""Installed IB client/transform exercised against a recording socket-free endpoint."""

from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace

import pytest
from nautilus_trader.adapters.interactive_brokers.common import IBContract, IBContractDetails
from nautilus_trader.adapters.interactive_brokers.parsing.instruments import (
    contract_details_to_dict,
)
from nautilus_trader.adapters.interactive_brokers.providers import (
    InteractiveBrokersInstrumentProvider,
)
from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import MessageBus
from nautilus_trader.core.uuid import UUID4
from nautilus_trader.execution.messages import SubmitOrder
from nautilus_trader.model.identifiers import AccountId, ClientId, TraderId, VenueOrderId
from nautilus_trader.model.instruments import Equity
from nautilus_trader.test_kit.stubs.events import TestEventStubs
from test_paper_execution import NOW, config, proposal, quote, snapshot
from test_paper_nautilus import ib_receipt, runtime

from drift.backtest.engine import make_instrument
from drift.data.model import DataError
from drift.execution import runtime as implementation
from drift.execution.ibkr import PAPER_CLIENT, node_config
from drift.execution.runtime import PaperCallbacks, build_paper_node, paper_exec_factory


def inline(coroutine):
    """These mocked async boundaries complete without I/O or an asyncio socketpair."""
    try:
        coroutine.send(None)
    except StopIteration as result:
        return result.value
    finally:
        coroutine.close()
    pytest.fail("unexpected asynchronous I/O")


def sdk_runtime(tmp_path, monkeypatch):
    gate, transport, endpoint, _, _ = runtime(tmp_path)
    cfg = node_config(gate.config).exec_clients[PAPER_CLIENT]
    cache = Cache()
    messages, sent = [], []
    raw = SimpleNamespace(
        is_ready=True,
        accounts=lambda: {gate.config.account_id},
        next_order_id=lambda: 17,
        place_order=sent.append,
    )
    provider = InteractiveBrokersInstrumentProvider(
        client=raw, clock=endpoint.clock, config=cfg.instrument_provider
    )
    contract = IBContract(
        conId=123,
        symbol="NVDA",
        secType="STK",
        currency="USD",
        exchange="SMART",
        primaryExchange="NASDAQ",
    )
    details = IBContractDetails(contract=contract, priceMagnifier=1, minTick=0.01)
    instrument = make_instrument(gate.config.instrument)
    payload = Equity.to_dict(instrument) | {"info": contract_details_to_dict(details)}
    instrument = Equity.from_dict(payload)
    provider.add(instrument)
    provider.contract_details[instrument.id] = details
    provider.contract[instrument.id] = contract
    cache.add_instrument(instrument)
    bus = MessageBus(trader_id=TraderId("DRIFT-001"), clock=endpoint.clock)
    bus.register("ExecEngine.process", messages.append)
    monkeypatch.setattr(implementation, "get_cached_ib_client", lambda **kwargs: raw)
    monkeypatch.setattr(
        implementation,
        "get_cached_interactive_brokers_instrument_provider",
        lambda **kwargs: provider,
    )
    execution = paper_exec_factory(gate, transport).create(
        loop=SimpleNamespace(),
        name=PAPER_CLIENT,
        config=cfg,
        msgbus=bus,
        cache=cache,
        clock=endpoint.clock,
    )
    execution._set_connected(True)
    assert execution.paper_events().contract_id == 123
    return gate, transport, endpoint, execution, cache, sent, messages


def test_installed_native_client_transforms_one_reserved_order_and_never_resends(
    tmp_path, monkeypatch
):
    gate, _, endpoint, execution, cache, sent, _ = sdk_runtime(tmp_path, monkeypatch)
    gate.reconcile(snapshot(), {}, NOW)
    order = gate.submit(proposal(), quote(), NOW)
    native = endpoint.sent[0][0]
    cache.add_order(native, client_id=ClientId(PAPER_CLIENT))
    command = SubmitOrder(
        trader_id=native.trader_id,
        strategy_id=native.strategy_id,
        order=native,
        command_id=UUID4(),
        ts_init=NOW,
        client_id=ClientId(PAPER_CLIENT),
    )
    inline(execution._submit_order(command))
    assert len(sent) == 1 and gate.orders()[order.order_id] == "SENDING"
    wire = sent[0]
    assert wire.account == "DU1234567" and wire.contract.conId == 123
    assert wire.action == "BUY" and wire.totalQuantity == 2 and wire.tif == "IOC"
    assert wire.orderType == "LMT" and wire.lmtPrice == 100.01 and not wire.outsideRth
    assert wire.orderRef.startswith(order.order_id)
    with pytest.raises(DataError, match="already sent"):
        inline(execution._submit_order(command))
    assert len(sent) == 1
    gate.close()


def test_pending_fee_never_reaches_sdk_zero_commission_fallback(tmp_path, monkeypatch):
    gate, _, endpoint, execution, _, _, _ = sdk_runtime(tmp_path, monkeypatch)
    gate.reconcile(snapshot(), {}, NOW)
    order = gate.submit(proposal(), quote(), NOW)
    forwarded = []
    monkeypatch.setattr(
        implementation.InteractiveBrokersExecutionClient,
        "_on_exec_details",
        lambda self, *args: forwarded.append(args),
    )
    execution._on_exec_details(order.order_id, *ib_receipt(order, fee=None))
    assert not forwarded and gate._filled(order.order_id) == 2
    execution._on_exec_details(order.order_id, *ib_receipt(order, fee="0.35"))
    assert len(forwarded) == 1 and gate._filled(order.order_id) == 2
    gate.close()


def test_native_actor_identity_matches_order_strategy(tmp_path):
    gate, transport, _, _, _ = runtime(tmp_path)
    actor = PaperCallbacks(gate, transport)
    assert str(actor.id) == "PAPER-001"
    actor.on_stop()
    assert gate._meta("halt") == "paper_runtime_stopped"
    gate.close()


def test_connection_guard_precedes_factory_helpers_and_node_construction(tmp_path, monkeypatch):
    cfg = config(connection_authorized=False, orders_authorized=False)
    gate, transport, _, _, _ = runtime(tmp_path, cfg)
    monkeypatch.setattr(
        implementation,
        "get_cached_ib_client",
        lambda **kwargs: pytest.fail("must not start a client"),
    )
    factory = paper_exec_factory(gate, transport)
    with pytest.raises(DataError, match="unauthorized"):
        factory.create(
            None, PAPER_CLIENT, node_config(cfg).exec_clients[PAPER_CLIENT], None, None, None
        )
    with pytest.raises(DataError, match="not authorized"):
        build_paper_node(gate, transport)
    gate.close()


@pytest.mark.parametrize("name", ["IB", "IB-PAPER", "LIVE"])
def test_factory_rejects_ambiguous_routes_before_starting_client(tmp_path, monkeypatch, name):
    gate, transport, _, _, _ = runtime(tmp_path)
    monkeypatch.setattr(
        implementation,
        "get_cached_ib_client",
        lambda **kwargs: pytest.fail("must not start a client"),
    )
    with pytest.raises(DataError, match="inconsistent"):
        paper_exec_factory(gate, transport).create(
            None, name, node_config(gate.config).exec_clients[PAPER_CLIENT], None, None, None
        )
    gate.close()


def test_changed_native_quantity_and_expired_approval_never_reach_wire(tmp_path, monkeypatch):
    gate, _, endpoint, execution, cache, sent, _ = sdk_runtime(tmp_path, monkeypatch)
    gate.reconcile(snapshot(), {}, NOW)
    order = gate.submit(proposal(), quote(), NOW)
    forged = replace(order, quantity=100).native()
    with pytest.raises(DataError, match="differs"):
        inline(execution._submit_order(SimpleNamespace(order=forged, params=None)))
    assert not sent
    gate.close()


def test_inferred_fills_and_sensitive_vendor_logging_disabled():
    prepared = node_config(config())
    assert not prepared.exec_engine.reconciliation
    assert not prepared.exec_engine.generate_missing_orders
    assert prepared.exec_engine.inflight_check_interval_ms == 0
    assert prepared.logging.log_level == "OFF" and not prepared.logging.bypass_logging


def broker_replies(execution, *, cash="10000", positions=(), open_orders=(), executions=()):
    async def reply(value):
        return value

    raw = execution._client
    raw.get_executions = lambda account: reply(executions)
    raw.get_positions = lambda account: reply(positions)
    raw.get_open_orders = lambda account: reply(open_orders)
    raw.subscribe_account_summary = lambda: execution._on_account_summary(
        "TotalCashValue", cash, "USD"
    )


def test_raw_broker_refresh_reconciles_fresh_cash_and_explicit_empty_replies(tmp_path, monkeypatch):
    gate, _, _, execution, _, sent, _ = sdk_runtime(tmp_path, monkeypatch)
    broker_replies(execution)
    state = inline(execution.refresh_snapshot(loss_today=Decimal(0)))
    assert state.cash == 10000 and state.position == 0 and state.available_at == NOW
    assert gate._ready and not sent
    gate.close()


@pytest.mark.parametrize("missing", ["positions", "open_orders", "executions"])
def test_unknown_broker_reply_cannot_become_empty(tmp_path, monkeypatch, missing):
    gate, _, _, execution, _, sent, _ = sdk_runtime(tmp_path, monkeypatch)
    broker_replies(execution, **{missing: None})
    with pytest.raises(DataError, match="refresh failed"):
        inline(execution.refresh_snapshot(loss_today=Decimal(0)))
    assert not gate._ready and not sent
    gate.close()


def test_missing_open_order_does_not_prove_cancellation_or_rejection(tmp_path, monkeypatch):
    gate, _, _, execution, _, sent, _ = sdk_runtime(tmp_path, monkeypatch)
    gate.reconcile(snapshot(), {}, NOW)
    order = gate.submit(proposal(), quote(), NOW)
    broker_replies(execution)
    with pytest.raises(DataError, match="refresh failed"):
        inline(execution.refresh_snapshot(loss_today=Decimal(0)))
    assert gate.orders()[order.order_id] == "SUBMITTED" and not sent
    gate.close()


def test_refresh_imports_confirmed_raw_execution_and_fee_before_reconciling(tmp_path, monkeypatch):
    gate, _, _, execution, _, _, _ = sdk_runtime(tmp_path, monkeypatch)
    gate.reconcile(snapshot(), {}, NOW)
    order = gate.submit(proposal(), quote(), NOW)
    fill, fee, contract = ib_receipt(order)
    fill.orderRef = order.order_id
    position = SimpleNamespace(account_id="DU1234567", contract=contract, quantity=Decimal(2))
    broker_replies(
        execution,
        cash="9799.63",
        positions=[position],
        executions=[{"execution": fill, "commission_report": fee, "contract": contract}],
    )
    state = inline(execution.refresh_snapshot(loss_today=Decimal("0.35")))
    assert state.position == 2 and gate.orders()[order.order_id] == "FILLED"
    assert gate._ledger() == (Decimal("9799.63"), 2)
    gate.close()


def test_real_native_node_builds_only_recording_clients_without_network(tmp_path, monkeypatch):
    import asyncio
    import socket

    import pytest_socket

    gate, transport, _, _, _, sent, _ = sdk_runtime(tmp_path, monkeypatch)
    node, loop = None, None

    # asyncio's wakeup socketpair is local AF_UNIX. TCP/UDP stay blocked throughout.
    class UnixOnly(socket.SocketType):
        def __new__(cls, family=-1, kind=-1, proto=-1, fileno=None):
            if family != socket.AF_UNIX:
                raise pytest_socket.SocketBlockedError()
            return super().__new__(cls, family, kind, proto, fileno)

    monkeypatch.setattr(socket, "socket", UnixOnly)
    try:
        loop = asyncio.new_event_loop()
        node = build_paper_node(gate, transport, loop)
        assert node.is_built()
        assert str(transport.strategy.id) == "PAPER-001"
        assert str(transport.strategy.trader_id) == "DRIFT-001"
        assert str(transport._client.account_id.get_id()) == "DU1234567"
        assert not sent and not gate._ready
    finally:
        if node is not None:
            node.dispose()
        if loop is not None and not loop.is_closed():
            loop.close()
        gate.close()


def test_cancel_rechecks_broker_order_identity_before_touching_wire(tmp_path, monkeypatch):
    gate, _, endpoint, execution, cache, _, _ = sdk_runtime(tmp_path, monkeypatch)
    gate.reconcile(snapshot(), {}, NOW)
    approved = gate.submit(proposal(), quote(), NOW)
    native = endpoint.sent[0][0]
    account = AccountId("IBPAPER-DU1234567")
    native.apply(TestEventStubs.order_submitted(native, account_id=account))
    native.apply(
        TestEventStubs.order_accepted(native, account_id=account, venue_order_id=VenueOrderId("17"))
    )
    cache.add_order(native, client_id=ClientId(PAPER_CLIENT))
    gate.acknowledge(approved.order_id)
    gate.kill()
    cancelled = []
    execution._client.cancel_order = cancelled.append
    command = SimpleNamespace(
        client_order_id=native.client_order_id,
        venue_order_id=VenueOrderId("99"),
        instrument_id=native.instrument_id,
        strategy_id=native.strategy_id,
    )
    with pytest.raises(DataError, match="matching confirmed"):
        inline(execution._cancel_order(command))
    assert not cancelled
    command.venue_order_id = native.venue_order_id
    inline(execution._cancel_order(command))
    assert cancelled == [17]
    gate.close()


def test_unreviewed_broker_price_units_block_execution(tmp_path, monkeypatch):
    gate, _, _, execution, _, sent, _ = sdk_runtime(tmp_path, monkeypatch)
    instrument = make_instrument(gate.config.instrument)
    details = execution.instrument_provider.contract_details[instrument.id]
    execution.instrument_provider.contract_details[instrument.id] = IBContractDetails(
        contract=details.contract, minTick=0.01, priceMagnifier=100
    )
    with pytest.raises(DataError, match="units/increments"):
        execution.paper_events()
    assert not sent
    gate.close()


def test_missing_session_risk_state_blocks_broker_refresh(tmp_path, monkeypatch):
    gate, _, _, execution, _, _, _ = sdk_runtime(tmp_path, monkeypatch)
    gate.reconcile(snapshot(), {}, NOW)
    assert gate._ready
    execution._client.get_executions = lambda *args: pytest.fail("must not read broker state")
    with pytest.raises(DataError, match="session loss is required"):
        inline(execution.refresh_snapshot(loss_today=Decimal("NaN")))
    assert not gate._ready
    assert gate._meta("halt") == "session_loss_unavailable"
    gate.close()
