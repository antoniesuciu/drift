"""Guarded integration with the installed IB execution client and native Strategy.

Construction is offline. Only build_paper_node/factory creation can initiate a connection,
and both check connection authorization first. Market feeds and strategy promotion are not
enabled here; complete broker reconciliation and verified live inputs still precede orders.
"""

import asyncio
from decimal import Decimal
from typing import Any

from nautilus_trader.adapters.interactive_brokers.execution import InteractiveBrokersExecutionClient
from nautilus_trader.adapters.interactive_brokers.factories import (
    get_cached_ib_client,
    get_cached_interactive_brokers_instrument_provider,
)
from nautilus_trader.config import StrategyConfig
from nautilus_trader.live.factories import LiveExecClientFactory
from nautilus_trader.model.enums import OrderSide, OrderType, TimeInForce
from nautilus_trader.model.identifiers import AccountId, InstrumentId
from nautilus_trader.trading.strategy import Strategy

from drift.data.model import DataError
from drift.execution.ibkr import PAPER_CLIENT, PaperConfig, node_config
from drift.execution.nautilus import NautilusPaperTransport, PaperEventBridge, _decimal
from drift.execution.paper import TERMINAL, PaperGate, Snapshot


class GuardedIBExecutionClient(InteractiveBrokersExecutionClient):
    def __init__(
        self, *args: Any, gate: PaperGate, transport: NautilusPaperTransport, **kwargs: Any
    ) -> None:
        super().__init__(*args, **kwargs)
        self._paper_gate, self._paper_transport = gate, transport
        self._paper_bridge: PaperEventBridge | None = None
        self._paper_cash: Decimal | None = None
        self._paper_cash_at = 0
        self._paper_cash_event = asyncio.Event()
        self._paper_refreshing = False

    def paper_events(self) -> PaperEventBridge:
        cfg = self._paper_gate.config
        instrument = self.instrument_provider.find(InstrumentId.from_str(cfg.instrument.id))
        if (
            instrument is None
            or str(instrument.quote_currency) != "USD"
            or instrument.price_increment.as_decimal() != cfg.instrument.tick
            or instrument.multiplier.as_decimal() != 1
            or instrument.size_increment.as_decimal() != 1
            or self.instrument_provider.get_price_magnifier(instrument.id) != 1
        ):
            self._paper_gate.halt("broker_instrument_mismatch")
            raise DataError("broker instrument identity/units/increments require review")
        try:
            contract = instrument.info["contract"]
            if (
                contract["symbol"] != cfg.instrument.symbol
                or contract["secType"] != "STK"
                or contract["currency"] != "USD"
            ):
                raise ValueError
            contract_id = contract["conId"]
            if self._paper_bridge is None:
                self._paper_bridge = PaperEventBridge(self._paper_gate, contract_id)
            if self._paper_bridge.contract_id != contract_id:
                raise ValueError
        except (ValueError, TypeError, KeyError):
            self._paper_gate.halt("broker_contract_unverified")
            raise DataError("resolved broker contract is absent, changed or incompatible") from None
        return self._paper_bridge

    async def _connect(self) -> None:
        await super()._connect()
        self._paper_transport.bind(self)
        self._paper_gate._accounts()
        self.paper_events()
        self._paper_gate.halt("startup_reconciliation_required")

    async def _disconnect(self) -> None:
        self._paper_gate.halt("broker_disconnected")
        await super()._disconnect()

    def _on_account_summary(self, tag: str, value: str, currency: str) -> None:
        if tag == "TotalCashValue" and currency == "USD":
            try:
                self._paper_cash = _decimal(value)
                self._paper_cash_at = self._clock.timestamp_ns()
                self._paper_cash_event.set()
            except DataError:
                self._paper_gate.halt("invalid_usd_cash")
                return
        super()._on_account_summary(tag, value, currency)

    async def refresh_snapshot(self, *, loss_today: Decimal, resume: bool = False) -> Snapshot:
        """Read-only full broker refresh. No missing reply is interpreted as zero/closed.

        The risk owner must supply measured session loss (no zero default). Raw executions
        are imported first; mutations during the remaining snapshot reads require a retry.
        Unknown non-open orders need definitive broker terminal proof or full executions.
        """
        gate, cfg = self._paper_gate, self._paper_gate.config
        if not isinstance(loss_today, Decimal) or not loss_today.is_finite() or loss_today < 0:
            gate.halt("session_loss_unavailable")
            raise DataError("measured finite nonnegative session loss is required")
        if self._paper_refreshing:
            raise DataError("paper broker refresh already in progress")
        self._paper_refreshing = True
        gate._ready = False
        try:
            gate._accounts()
            bridge = self.paper_events()
            executions = await self._client.get_executions(cfg.account_id)
            if executions is None:
                raise DataError("broker execution reply is unknown")
            for row in executions:
                execution = row["execution"]
                order_ref = execution.orderRef.rsplit(":", 1)[0]
                bridge.ib_execution(
                    order_ref, execution, row.get("commission_report"), row["contract"]
                )
            revision = gate.db.total_changes
            started = self._clock.timestamp_ns()
            self._paper_cash_event.clear()
            self._client.subscribe_account_summary()
            positions = await self._client.get_positions(cfg.account_id)
            open_orders = await self._client.get_open_orders(cfg.account_id)
            if positions is None or open_orders is None:
                raise DataError("broker position/open-order reply is unknown")
            if not self._paper_cash_event.is_set():
                await asyncio.wait_for(self._paper_cash_event.wait(), self._connection_timeout)
            if (
                self._paper_cash is None
                or self._paper_cash_at < started
                or gate.db.total_changes != revision
            ):
                raise DataError("broker changed during refresh or fresh USD cash is unavailable")
            quantity = Decimal(0)
            seen: set[int] = set()
            for row in positions:
                q = _decimal(row.quantity)
                if row.account_id != cfg.account_id:
                    raise DataError("broker position account differs from allow-list")
                if not q:
                    continue
                if (
                    row.contract.conId != bridge.contract_id
                    or row.contract.conId in seen
                    or q != q.to_integral()
                    or q < 0
                ):
                    raise DataError("external/duplicate/fractional/short broker position")
                seen.add(row.contract.conId)
                quantity += q
            reports: dict[str, str] = {}
            local = gate.orders()
            for raw in open_orders:
                oid = raw.orderRef
                if (
                    raw.account != cfg.account_id
                    or oid not in local
                    or oid in reports
                    or raw.contract.conId != bridge.contract_id
                ):
                    raise DataError("external/duplicate broker open order")
                filled = gate._filled(oid)
                reports[oid] = "PARTIAL" if filled else "ACK"
            for oid, status in local.items():
                if oid in reports:
                    continue
                if gate._filled(oid) == gate._order(oid).quantity:
                    reports[oid] = "FILLED"
                elif status in TERMINAL:
                    reports[oid] = status
                else:
                    raise DataError("missing open order has no definitive terminal proof")
            snapshot = Snapshot(self._paper_cash, int(quantity), started, loss_today)
            gate.reconcile(snapshot, reports, self._clock.timestamp_ns(), resume=resume)
            return snapshot
        except Exception:
            gate.halt("broker_refresh_unconfirmed")
            raise DataError("paper broker refresh failed; reconciliation required") from None
        finally:
            self._paper_refreshing = False

    async def _submit_order(self, command: Any) -> None:
        gate = self._paper_gate
        order = gate._order(str(command.order.client_order_id))
        native = command.order
        if (
            str(native.instrument_id) != order.instrument_id
            or str(native.trader_id) != "DRIFT-001"
            or str(native.strategy_id) != "PAPER-001"
            or native.side != (OrderSide.BUY if order.side == 1 else OrderSide.SELL)
            or native.order_type != OrderType.LIMIT
            or native.time_in_force != TimeInForce.IOC
            or native.quantity.as_decimal() != order.quantity
            or native.price.as_decimal() != order.limit
            or native.tags
            or command.params
        ):
            gate.halt("native_command_changed")
            raise DataError("native command differs from the approved paper reservation")
        self.paper_events()  # Effective broker identity/increments must still match.
        self._paper_transport.verify_native_position()
        gate.native_preflight(order, self._clock.timestamp_ns(), sending=True)
        try:
            # In installed 1.231 this coroutine has no await between this check and place_order.
            await super()._submit_order(command)
        except Exception:
            gate.halt("wire_submission_uncertain")
            raise DataError("IB submission requires reconciliation; diagnostics withheld") from None

    async def _cancel_order(self, command: Any) -> None:
        gate = self._paper_gate
        if (
            not gate.config.orders_authorized
            or gate.orders().get(str(command.client_order_id)) != "CANCEL_REQUESTED"
        ):
            raise DataError("IB cancellation has no authorized journaled request")
        gate._accounts()
        native = self._cache.order(command.client_order_id)
        if (
            native is None
            or native.venue_order_id is None
            or command.venue_order_id != native.venue_order_id
            or command.instrument_id != native.instrument_id
            or str(native.instrument_id) != gate._order(str(command.client_order_id)).instrument_id
        ):
            gate.halt("cancel_identity_unconfirmed")
            raise DataError("cancellation requires the matching confirmed broker order identity")
        await super()._cancel_order(command)

    async def _submit_order_list(self, command: Any) -> None:
        self._paper_gate.halt("unsupported_batch_order")
        raise DataError("paper order batches are unsupported")

    async def _modify_order(self, command: Any) -> None:
        self._paper_gate.halt("unsupported_order_modification")
        raise DataError("paper order modification is unsupported; reconcile instead")

    async def _cancel_all_orders(self, command: Any) -> None:
        self._paper_gate.halt("unsupported_unscoped_cancel")
        raise DataError("paper cancellation must identify each journaled order")

    def _on_exec_details(
        self, order_ref: str, execution: Any, commission_report: Any, contract: Any
    ) -> None:
        try:
            bridge = self.paper_events()
            bridge.ib_execution(order_ref, execution, commission_report, contract)
            quantity = execution.shares
            if not self._paper_gate.confirmed_fill(str(execution.execId), order_ref, int(quantity)):
                return  # Preserve raw shares, but never let the SDK invent a zero fee.
        except DataError:
            return  # Gate is halted; broker reconciliation must resolve the receipt.
        super()._on_exec_details(order_ref, execution, commission_report, contract)

    def _on_order_status(self, order_ref: str, order_status: str, **kwargs: Any) -> None:
        try:
            self.paper_events().ib_status(
                order_ref,
                order_status,
                kwargs.get("filled", 0),
                kwargs.get("remaining", 0),
                self._paper_gate.config.account_id,
            )
        except DataError:
            return
        super()._on_order_status(order_ref, order_status, **kwargs)

    def _on_open_order(self, order_ref: str, order: Any, order_state: Any) -> None:
        try:
            expected = self._paper_gate._order(order_ref)
            bridge = self.paper_events()
            if (
                order.account != self._paper_gate.config.account_id
                or order.contract.conId != bridge.contract_id
                or order.action != ("BUY" if expected.side == 1 else "SELL")
                or _decimal(order.totalQuantity) != expected.quantity
                or _decimal(order.lmtPrice) != expected.limit
                or order.tif != "IOC"
                or order.orderType != "LMT"
                or order.outsideRth
                or order.whatIf
            ):
                raise DataError("broker open order differs from the approved intent")
        except (DataError, AttributeError):
            self._paper_gate.halt("unconfirmed_or_external_open_order")
            return
        super()._on_open_order(order_ref, order, order_state)


def paper_exec_factory(
    gate: PaperGate, transport: NautilusPaperTransport
) -> type[LiveExecClientFactory]:
    """One explicitly configured paper execution route; no global application registry."""

    class Factory(LiveExecClientFactory):
        @staticmethod
        def create(loop: Any, name: str, config: Any, msgbus: Any, cache: Any, clock: Any) -> Any:
            cfg = gate.config
            if not isinstance(cfg, PaperConfig):
                raise DataError("IBKR runtime requires its own paper configuration")
            if (
                not cfg.connection_authorized
                or name != PAPER_CLIENT
                or config.account_id != cfg.account_id
                or config.ibg_host != cfg.host
                or config.ibg_port != cfg.port
                or config.ibg_client_id != cfg.client_id
                or config.dockerized_gateway is not None
            ):
                raise DataError("paper connection configuration is unauthorized or inconsistent")
            # The installed helper starts networking here, before TradingNode.run().
            client = get_cached_ib_client(
                loop=loop,
                msgbus=msgbus,
                cache=cache,
                clock=clock,
                host=cfg.host,
                port=cfg.port,
                client_id=cfg.client_id,
                dockerized_gateway=None,
                fetch_all_open_orders=True,
                request_timeout_secs=config.request_timeout_secs,
            )
            provider = get_cached_interactive_brokers_instrument_provider(
                client=client, clock=clock, config=config.instrument_provider
            )
            execution = GuardedIBExecutionClient(
                loop=loop,
                client=client,
                account_id=AccountId(f"{PAPER_CLIENT}-{cfg.account_id}"),
                msgbus=msgbus,
                cache=cache,
                clock=clock,
                instrument_provider=provider,
                config=config,
                name=PAPER_CLIENT,
                connection_timeout=config.connection_timeout,
                gate=gate,
                transport=transport,
            )
            transport.bind(execution)
            return execution

    return Factory


class PaperCallbacks(Strategy):
    """Native callback adapter; proposal generation/market data remain separate inputs."""

    def __init__(self, gate: PaperGate, transport: NautilusPaperTransport) -> None:
        super().__init__(
            StrategyConfig(
                strategy_id="PAPER",  # 1.231 expects a string and appends order_id_tag.
                order_id_tag="001",
                manage_stop=False,
                log_events=False,
                log_commands=False,
            )
        )
        self._gate, self._transport = gate, transport

    def on_order_event(self, event: Any) -> None:
        try:
            self._transport._client.paper_events().native_event(event)
        except (DataError, AttributeError):
            self._gate.halt("native_callback_unconfirmed")

    def on_stop(self) -> None:
        self._gate.halt("paper_runtime_stopped")


def build_paper_node(gate: PaperGate, transport: NautilusPaperTransport, loop: Any = None) -> Any:
    """Connection boundary. Call only for a ready, explicitly authorized paper session."""
    if (
        not isinstance(gate.config, PaperConfig)
        or not gate.config.connection_authorized
        or gate.transport is not transport
    ):
        raise DataError("paper node connection is not authorized or gate/transport differs")
    from nautilus_trader.live.node import TradingNode

    node = TradingNode(config=node_config(gate.config), loop=loop)
    callbacks = PaperCallbacks(gate, transport)
    transport.strategy = callbacks
    node.trader.add_strategy(callbacks)
    node.add_exec_client_factory(PAPER_CLIENT, paper_exec_factory(gate, transport))
    node.build()
    return node
