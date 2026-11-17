"""Shared paper risk configuration and approved order; broker lifecycle stays in adapters."""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, ClassVar

from drift.backtest.data import InstrumentSpec
from drift.backtest.risk import RiskLimits, Sizing
from drift.data.model import DataError


@dataclass(frozen=True, slots=True)
class PaperPolicy:
    account_id: str = field(repr=False)
    instrument: InstrumentSpec
    risk: RiskLimits
    sizing: Sizing
    capital_limit: Decimal
    min_order_interval_seconds: int
    state_max_age_seconds: int
    connection_authorized: bool = False
    orders_authorized: bool = False
    broker: ClassVar[str] = ""

    def __post_init__(self) -> None:
        if self.broker not in ("ibkr", "alpaca") or not self.account_id:
            raise DataError("an explicit paper broker/account is required")
        if (
            self.instrument.kind != "equity"
            or self.instrument.currency != "USD"
            or self.instrument.multiplier != 1
            or self.instrument.lot != 1
        ):
            raise DataError("paper policy supports USD equities in whole shares only")
        for value in (
            self.capital_limit,
            self.risk.max_quantity,
            self.risk.max_notional,
            self.risk.max_leverage,
            self.risk.max_session_loss,
            self.sizing.amount,
        ):
            if not value.is_finite() or value <= 0:
                raise DataError("finite positive paper limits required")
        for timing in (
            self.min_order_interval_seconds,
            self.state_max_age_seconds,
            self.risk.max_data_age_seconds,
            self.risk.max_entries_per_session,
        ):
            if type(timing) is not int or timing < 1:
                raise DataError("explicit positive paper timing/rate limits required")
        if (
            self.sizing.mode != "fixed_quantity"
            or self.sizing.amount != self.sizing.amount.to_integral()
        ):
            raise DataError("paper execution supports fixed whole-share sizing only")
        if type(self.connection_authorized) is not bool or type(self.orders_authorized) is not bool:
            raise DataError("authorization flags must be booleans")
        if self.orders_authorized and not self.connection_authorized:
            raise DataError("order authorization requires connection authorization")


@dataclass(frozen=True, slots=True)
class PaperOrder:
    order_id: str
    proposal_id: str
    instrument_id: str
    side: int
    quantity: int
    limit: Decimal
    created_at: int
    valid_until: int = 0

    def native(self) -> Any:
        """Translate a risk-approved intent into the installed IB adapter's native input."""
        from nautilus_trader.core.uuid import UUID4
        from nautilus_trader.model.enums import OrderSide, TimeInForce
        from nautilus_trader.model.identifiers import (
            ClientOrderId,
            InstrumentId,
            StrategyId,
            TraderId,
        )
        from nautilus_trader.model.objects import Price, Quantity
        from nautilus_trader.model.orders import LimitOrder

        return LimitOrder(
            trader_id=TraderId("DRIFT-001"),
            strategy_id=StrategyId("PAPER-001"),
            instrument_id=InstrumentId.from_str(self.instrument_id),
            client_order_id=ClientOrderId(self.order_id),
            order_side=OrderSide.BUY if self.side == 1 else OrderSide.SELL,
            quantity=Quantity.from_int(self.quantity),
            price=Price.from_str(str(self.limit)),
            init_id=UUID4(),
            ts_init=self.created_at,
            time_in_force=TimeInForce.IOC,
        )
