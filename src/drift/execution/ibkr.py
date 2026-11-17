"""Offline IBKR paper preparation using the already locked Nautilus adapter.

Configuration and order translation only: this module never constructs/runs a TradingNode,
connects to TWS, discovers credentials or submits an order. Paper ports alone are not proof
of account identity; the paper gate also checks the actual managed-account response.
"""

import re
from dataclasses import dataclass
from typing import Any, ClassVar

from drift.data.model import DataError
from drift.execution.model import PaperOrder as PaperOrder
from drift.execution.model import PaperPolicy

PAPER_CLIENT = "IBPAPER"  # 1.231 splits client keys/account components at '-'.


@dataclass(frozen=True, slots=True)
class PaperConfig(PaperPolicy):
    """Retained IBKR configuration; Alpaca is the active paper adapter."""

    host: str = "127.0.0.1"
    port: int = 7497
    client_id: int = 37
    broker: ClassVar[str] = "ibkr"

    def __post_init__(self) -> None:
        PaperPolicy.__post_init__(self)
        if (
            not re.fullmatch(r"DU[0-9]{5,12}", self.account_id)
            or self.host != "127.0.0.1"
            or self.port not in (7497, 4002)
            or type(self.client_id) is not int
            or not 1 <= self.client_id <= 999
            or self.instrument.venue != "XNAS"
        ):
            raise DataError("paper-only loopback/account/equity configuration required")


def node_config(config: PaperConfig) -> Any:
    """Build the real installed adapter's config, without side effects or gateway startup.

    The runtime safety/event bridge is deliberately not activated by returning configuration.
    No broker username/password, Docker gateway or environment account fallback is used.
    """
    from nautilus_trader.adapters.interactive_brokers.common import IBContract
    from nautilus_trader.adapters.interactive_brokers.config import (
        InteractiveBrokersExecClientConfig,
        InteractiveBrokersInstrumentProviderConfig,
    )
    from nautilus_trader.config import (
        LiveExecEngineConfig,
        LiveRiskEngineConfig,
        LoggingConfig,
        RoutingConfig,
        TradingNodeConfig,
    )
    from nautilus_trader.model.identifiers import TraderId

    contract = IBContract(
        symbol=config.instrument.symbol,
        secType="STK",
        exchange="SMART",
        primaryExchange="NASDAQ",
        currency="USD",
    )
    provider = InteractiveBrokersInstrumentProviderConfig(
        load_contracts=frozenset({contract}),
        convert_exchange_to_mic_venue=True,
        symbol_to_mic_venue={config.instrument.symbol: config.instrument.venue},
    )
    execution = InteractiveBrokersExecClientConfig(
        ibg_host=config.host,
        ibg_port=config.port,
        ibg_client_id=config.client_id,
        account_id=config.account_id,
        instrument_provider=provider,
        fetch_all_open_orders=True,
        routing=RoutingConfig(default=False),
        connection_timeout=10,
        request_timeout_secs=10,
    )
    return TradingNodeConfig(
        trader_id=TraderId("DRIFT-001"),
        exec_clients={PAPER_CLIENT: execution},
        # LIVE-mode kernels reject bypass_logging. Keep vendor account details off stdout;
        # the paper journal carries sanitized lifecycle/halt state.
        logging=LoggingConfig(log_level="OFF", bypass_logging=False),
        exec_engine=LiveExecEngineConfig(
            reconciliation=False,
            generate_missing_orders=False,
            inflight_check_interval_ms=0,
        ),  # The gate reconciles raw broker receipts; never manufacture fills from positions.
        risk_engine=LiveRiskEngineConfig(
            bypass=False,
            max_order_submit_rate="1/00:00:01",
            max_notional_per_order={config.instrument.id: int(config.risk.max_notional)},
        ),
    )
