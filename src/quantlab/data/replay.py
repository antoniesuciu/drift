"""Order-free replay of verified native Parquet rows through NautilusTrader."""

from pathlib import Path
from typing import Any

from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.common.actor import Actor
from nautilus_trader.config import BacktestEngineConfig, LoggingConfig
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.data import Bar
from nautilus_trader.model.enums import AccountType, OmsType
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.objects import Money

from quantlab.data.model import DataError, canonical, digest
from quantlab.data.store import load_dataset


class _Observer(Actor):
    def __init__(self, bars: list[Any]) -> None:
        super().__init__()
        self.types = {b.bar_type for b in bars}
        self.events: list[tuple[str, int, int, str]] = []

    def on_start(self) -> None:
        for bar_type in sorted(self.types, key=str):
            self.subscribe_bars(bar_type)

    def on_bar(self, bar: Bar) -> None:
        self.events.append(
            (
                str(bar.bar_type.instrument_id),
                bar.ts_event,
                self.clock.timestamp_ns(),
                str(bar.close),
            )
        )


def replay_dataset(path: Path) -> dict[str, Any]:
    dataset = load_dataset(path)
    observer = _Observer(dataset.bars)
    engine = BacktestEngine(
        BacktestEngineConfig(logging=LoggingConfig(bypass_logging=True), run_analysis=False)
    )
    try:
        engine.add_venue(
            venue=Venue("CME"),
            oms_type=OmsType.NETTING,
            account_type=AccountType.MARGIN,
            starting_balances=[Money(10_000, USD)],
            base_currency=USD,
        )
        for instrument in dataset.instruments:
            engine.add_instrument(instrument)
        engine.add_actor(observer)
        engine.add_data(dataset.bars)
        engine.run()
        result = engine.get_result()
        expected = [
            (str(b.bar_type.instrument_id), b.ts_event, b.ts_init, str(b.close))
            for b in dataset.bars
        ]
        if observer.events != expected or result.total_orders or result.total_positions:
            raise DataError("replay observations/availability/order-free invariant failed")
        return {
            "synthetic": True,
            "dataset_version": path.name,
            "bars": len(expected),
            "iterations": result.iterations,
            "orders": result.total_orders,
            "positions": result.total_positions,
            "observations_sha256": digest(canonical(expected)),
            "first_available_ns": expected[0][2],
            "last_available_ns": expected[-1][2],
        }
    finally:
        engine.dispose()
