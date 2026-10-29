"""Small synthetic MES replay through NautilusTrader, with observation only.

No strategy, orders, broker adapter, external files or network client is created.
Prices, contract dates and account balance are fixtures, not real market observations.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import nautilus_trader
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.common.actor import Actor
from nautilus_trader.config import BacktestEngineConfig, LoggingConfig
from nautilus_trader.core.datetime import dt_to_unix_nanos
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import AccountType, AssetClass, OmsType
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.instruments import FuturesContract
from nautilus_trader.model.objects import Money, Price, Quantity

from quantlab.time import BarInterval


@dataclass(frozen=True, slots=True)
class SmokeConfig:
    """Bound the offline fixture size and modeled delivery latency."""

    bar_count: int = 3
    delivery_delay: timedelta = timedelta(milliseconds=100)

    def __post_init__(self) -> None:
        if type(self.bar_count) is not int or not 1 <= self.bar_count <= 10:
            raise ValueError("bar_count must be an integer between 1 and 10")
        if not isinstance(self.delivery_delay, timedelta) or not (
            timedelta(0) <= self.delivery_delay < timedelta(minutes=1)
        ):
            raise ValueError("delivery_delay must be a timedelta from zero to under one minute")


@dataclass(frozen=True, slots=True)
class SmokeReport:
    """Deterministic engine observations; deliberately excludes wall clock/run UUIDs."""

    synthetic: bool
    framework_version: str
    instrument_id: str
    tick_value_usd: str
    event_times_ns: tuple[int, ...]
    observed_times_ns: tuple[int, ...]
    closes: tuple[str, ...]
    iterations: int
    total_orders: int
    total_positions: int


class _BarObserver(Actor):
    """Read-only engine callback probe, not a trading strategy."""

    def __init__(self, bar_type: BarType) -> None:
        super().__init__()
        self.bar_type = bar_type
        self.event_times: list[int] = []
        self.observed_times: list[int] = []
        self.closes: list[str] = []

    def on_start(self) -> None:
        self.subscribe_bars(self.bar_type)

    def on_bar(self, bar: Bar) -> None:
        self.event_times.append(bar.ts_event)
        self.observed_times.append(self.clock.timestamp_ns())
        self.closes.append(str(bar.close))


def run_smoke(config: SmokeConfig | None = None) -> SmokeReport:
    """Run a fresh, in-memory engine and dispose it even on failure."""
    config = SmokeConfig() if config is None else config
    if not isinstance(config, SmokeConfig):
        raise ValueError("config must be SmokeConfig")
    instrument = FuturesContract(
        instrument_id=InstrumentId.from_str("MESZ6.CME"),
        raw_symbol=Symbol("MESZ6"),
        asset_class=AssetClass.INDEX,
        currency=USD,
        price_precision=2,
        price_increment=Price.from_str("0.25"),
        multiplier=Quantity.from_int(5),
        lot_size=Quantity.from_int(1),
        underlying="SPX",
        activation_ns=dt_to_unix_nanos(datetime(2026, 1, 1, tzinfo=UTC)),
        expiration_ns=dt_to_unix_nanos(datetime(2026, 12, 18, 14, 30, tzinfo=UTC)),
        ts_event=0,
        ts_init=0,
        info={"synthetic": True},
    )
    bar_type = BarType.from_str("MESZ6.CME-1-MINUTE-LAST-EXTERNAL")
    start = datetime(2026, 3, 9, 13, 30, tzinfo=UTC)
    bars = []
    for index in range(config.bar_count):
        end = start + timedelta(minutes=index + 1)
        interval = BarInterval(end - timedelta(minutes=1), end, end + config.delivery_delay)
        price = Decimal("5000.00") + Decimal("0.25") * index
        bars.append(
            Bar(
                bar_type=bar_type,
                open=Price.from_str(f"{price:.2f}"),
                high=Price.from_str(f"{price + Decimal('0.50'):.2f}"),
                low=Price.from_str(f"{price - Decimal('0.50'):.2f}"),
                close=Price.from_str(f"{price + Decimal('0.25'):.2f}"),
                volume=Quantity.from_int(10),
                ts_event=dt_to_unix_nanos(interval.end),
                ts_init=dt_to_unix_nanos(interval.available_at),
            )
        )

    observer = _BarObserver(bar_type)
    engine = BacktestEngine(
        config=BacktestEngineConfig(logging=LoggingConfig(bypass_logging=True), run_analysis=False)
    )
    try:
        engine.add_venue(
            venue=Venue("CME"),
            oms_type=OmsType.NETTING,
            account_type=AccountType.MARGIN,
            starting_balances=[Money(10_000, USD)],
            base_currency=USD,
        )
        engine.add_instrument(instrument)
        engine.add_actor(observer)
        engine.add_data(bars)
        engine.run()
        result = engine.get_result()
        return SmokeReport(
            synthetic=True,
            framework_version=nautilus_trader.__version__,
            instrument_id=str(instrument.id),
            tick_value_usd=str(instrument.price_increment.as_decimal() * instrument.multiplier),
            event_times_ns=tuple(observer.event_times),
            observed_times_ns=tuple(observer.observed_times),
            closes=tuple(observer.closes),
            iterations=result.iterations,
            total_orders=result.total_orders,
            total_positions=result.total_positions,
        )
    finally:
        engine.dispose()
