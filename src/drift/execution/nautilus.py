"""Pinned Nautilus/IB order and callback translation through the paper gate.

No node construction or connection occurs on import/construction. The raw IB execution
receipt, not a possibly rounded native fill/placeholder commission, owns the cash journal.
"""

from decimal import Decimal, InvalidOperation
from typing import Any

from nautilus_trader.model.enums import OrderSide, PositionSide
from nautilus_trader.model.events import (
    OrderAccepted,
    OrderCanceled,
    OrderCancelRejected,
    OrderDenied,
    OrderExpired,
    OrderFilled,
    OrderRejected,
)
from nautilus_trader.model.identifiers import ClientId, ClientOrderId

from drift.data.model import DataError
from drift.execution.ibkr import PAPER_CLIENT, PaperConfig, PaperOrder
from drift.execution.paper import PaperGate


class NautilusPaperTransport:
    """Use the real strategy's risk/execution route, with an explicitly bound IB client.

    Never call IB placeOrder directly. Client readiness/account and native strategy identity
    are checked on every request; public configuration alone cannot authorize this route.
    """

    def __init__(self, config: PaperConfig, strategy: Any) -> None:
        self.config, self.strategy = config, strategy
        self._client: Any = None
        self._gate: PaperGate | None = None

    def attach(self, gate: PaperGate) -> None:
        if gate.config != self.config:
            raise DataError("paper gate and native transport configuration differ")
        self._gate = gate

    def bind(self, execution_client: Any) -> None:
        if str(execution_client.account_id) != PAPER_CLIENT + "-" + self.config.account_id:
            raise DataError("native execution account/route differs from paper configuration")
        self._client = execution_client

    def managed_accounts(self) -> tuple[str, ...]:
        if not self.config.connection_authorized or self._client is None:
            raise DataError("paper connection is not authorized/bound")
        if not self._client.is_connected or not self._client._client.is_ready:
            raise DataError("IB paper client is not ready")
        return tuple(sorted(self._client._client.accounts()))

    def _preflight(self) -> None:
        if not self.config.orders_authorized:
            raise DataError("paper orders are not authorized")
        if self.managed_accounts() != (self.config.account_id,):
            raise DataError("native managed account differs from paper allow-list")
        if str(self.strategy.trader_id) != "DRIFT-001" or str(self.strategy.id) != "PAPER-001":
            raise DataError("native strategy/trader identity differs from the paper order route")

    def submit(self, order: PaperOrder) -> None:
        self._preflight()
        if self._gate is None:
            raise DataError("native transport has no shared paper risk gate")
        if self._gate.orders().get(order.order_id) != "PREPARED":
            raise DataError("native order has already been queued or has no reservation")
        self.verify_native_position()
        self._gate.native_preflight(order, self.strategy.clock.timestamp_ns())
        self.strategy.submit_order(order.native(), client_id=ClientId(PAPER_CLIENT))

    def verify_native_position(self) -> None:
        if self._gate is None:
            raise DataError("native transport has no shared paper risk gate")
        from nautilus_trader.model.identifiers import InstrumentId

        positions = self.strategy.cache.positions_open(
            instrument_id=InstrumentId.from_str(self.config.instrument.id)
        )
        account = PAPER_CLIENT + "-" + self.config.account_id
        if len(positions) > 1 or any(str(p.account_id) != account for p in positions):
            self._gate.halt("native_position_scope_mismatch")
            raise DataError("native position scope differs from the isolated paper account")
        native = sum(
            (
                p.quantity.as_decimal() * (1 if p.side == PositionSide.LONG else -1)
                for p in positions
            ),
            Decimal(0),
        )
        if native != self._gate._ledger()[1]:
            self._gate.halt("native_position_mismatch")
            raise DataError("native position differs from the raw execution journal")

    def cancel(self, order_id: str) -> None:
        self._preflight()
        if self._gate is None or self._gate.orders().get(order_id) != "CANCEL_REQUESTED":
            raise DataError("native cancellation has no journaled request")
        order = self.strategy.cache.order(ClientOrderId(order_id))
        if order is None:
            raise DataError("native order is unknown; cancellation requires reconciliation")
        self.strategy.cancel_order(order, client_id=ClientId(PAPER_CLIENT))


def _decimal(value: Any) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, str | int | float | Decimal):
        raise DataError("invalid broker numeric value")
    try:
        result = Decimal(str(value))  # IB exposes prices/fees as floats; no extra float arithmetic.
        if not result.is_finite():
            raise InvalidOperation
        return result
    except (ValueError, InvalidOperation):
        raise DataError("invalid broker numeric value") from None


class PaperEventBridge:
    """Translate validated IB receipts and actual Nautilus event objects into one journal."""

    def __init__(self, gate: PaperGate, contract_id: int) -> None:
        if type(contract_id) is not int or contract_id < 1:
            raise DataError("resolved positive IB contract identity required")
        self.gate, self.contract_id = gate, contract_id

    def ib_execution(self, order_ref: str, execution: Any, commission: Any, contract: Any) -> None:
        """Called with raw IB execution/commission fields before native fill generation.

        A pending fee stays unknown. Nautilus 1.231.0's zero placeholder is not evidence.
        Repeated complete receipts resolve unknown fees without duplicating shares.
        """
        cfg = self.gate.config
        try:
            order = self.gate._order(order_ref)
            if (
                execution.acctNumber != cfg.account_id
                or contract.conId != self.contract_id
                or contract.symbol != cfg.instrument.symbol
                or contract.secType != "STK"
                or contract.currency != "USD"
                or execution.side != ("BOT" if order.side == 1 else "SLD")
            ):
                raise DataError("IB execution account/contract/side differs from approved intent")
            quantity = _decimal(execution.shares)
            if quantity != quantity.to_integral():
                raise DataError("fractional broker execution is unsupported")
            fee = None
            if not isinstance(execution.execId, str) or not execution.execId:
                raise DataError("invalid broker execution identity")
            if commission is not None and getattr(commission, "execId", None) != execution.execId:
                raise DataError("execution/commission identity differs")
            amount = getattr(commission, "commissionAndFees", None)
            if amount is not None:
                candidate = _decimal(amount)
                # Official IB UNSET_DOUBLE plus -1/None pending conventions.
                if candidate not in (Decimal(-1), Decimal("1.7976931348623157E+308")):
                    if getattr(commission, "currency", None) == "USD":
                        fee = candidate
            self.gate.record_fill(
                str(execution.execId), order_ref, int(quantity), _decimal(execution.price), fee
            )
        except Exception:
            self.gate.halt("invalid_or_unconfirmed_ib_execution")
            raise DataError("IB execution requires reconciliation; diagnostics withheld") from None

    def native_event(self, event: Any) -> None:
        try:
            order_id = str(event.client_order_id)
            order = self.gate._order(order_id)
            if (
                str(event.trader_id) != "DRIFT-001"
                or str(event.strategy_id) != "PAPER-001"
                or str(event.instrument_id) != order.instrument_id
            ):
                raise DataError("native event identity differs from approved intent")
            account = getattr(event, "account_id", None)
            if account is None and isinstance(
                event, OrderAccepted | OrderFilled | OrderRejected | OrderCanceled | OrderExpired
            ):
                raise DataError("broker event lacks an account identity")
            if (
                account is not None
                and str(account) != PAPER_CLIENT + "-" + self.gate.config.account_id
            ):
                raise DataError("native event account differs from paper allow-list")
            if isinstance(event, OrderAccepted):
                self.gate.acknowledge(order_id)
            elif isinstance(event, OrderFilled):
                quantity = event.last_qty.as_decimal()
                if (
                    quantity != quantity.to_integral()
                    or event.order_side != (OrderSide.BUY if order.side == 1 else OrderSide.SELL)
                    or not self.gate.confirmed_fill(str(event.trade_id), order_id, int(quantity))
                ):
                    raise DataError("native fill lacks matching confirmed raw IB execution/fee")
            elif isinstance(event, OrderRejected | OrderDenied):
                if self.gate.orders()[order_id] not in ("PREPARED", "SUBMITTED", "REJECTED"):
                    raise DataError("native rejection after wire submission needs broker proof")
                self.gate.terminal(order_id, "REJECTED")
            elif isinstance(event, OrderCanceled | OrderExpired):
                if self.gate.orders()[order_id] not in ("CANCELLED", "FILLED"):
                    raise DataError("native cancellation lacks matching raw broker status")
            elif isinstance(event, OrderCancelRejected):
                raise DataError("cancellation rejected; reservation remains unresolved")
        except Exception:
            self.gate.halt("unconfirmed_native_event")
            raise DataError(
                "native paper event requires reconciliation; diagnostics withheld"
            ) from None

    def disconnected(self) -> None:
        self.gate.halt("broker_disconnected")

    def ib_status(
        self, order_id: str, status: str, filled: Any, remaining: Any, account: str
    ) -> None:
        try:
            order = self.gate._order(order_id)
            quantity, rest = _decimal(filled), _decimal(remaining)
            if (
                account != self.gate.config.account_id
                or quantity != quantity.to_integral()
                or rest != rest.to_integral()
                or quantity < 0
                or rest < 0
                or quantity + rest > order.quantity
            ):
                raise DataError("invalid broker order status")
            self.gate.broker_filled(order_id, int(quantity))
            if status in ("Submitted", "PreSubmitted"):
                self.gate.acknowledge(order_id)
            elif status in ("Cancelled", "ApiCancelled"):
                self.gate.terminal(order_id, "CANCELLED")
            elif status == "Inactive":
                raise DataError("inactive broker order is not definitive rejection evidence")
            elif status not in ("Filled", "PendingCancel", "PendingSubmit", "ApiPending"):
                raise DataError("unsupported broker order status")
        except Exception:
            self.gate.halt("unresolved_ib_order_status")
            raise DataError(
                "IB order status requires reconciliation; diagnostics withheld"
            ) from None
