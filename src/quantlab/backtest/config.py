"""Validated backtest configuration. Costs, sizing and risk have no defaults (deny by default);
strategy parameters fall back to documented, version-tagged values that are recorded in the
resolved configuration, so a report always shows exactly what ran."""

from dataclasses import MISSING, dataclass, fields, is_dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from quantlab.backtest.data import InstrumentSpec, SyntheticSpec
from quantlab.backtest.risk import ExitPolicy, Protection, RiskLimits, Sizing
from quantlab.data.model import DataError, token
from quantlab.data.model import fields as exact_fields
from quantlab.strategies.rule.candlestick.filters import (
    Filters,
    LevelFilter,
    TrendFilter,
    VolatilityFilter,
    VolumeFilter,
)
from quantlab.strategies.rule.candlestick.patterns import DetectorConfig
from quantlab.strategies.rule.candlestick.policy import CandlestickParams
from quantlab.strategies.rule.statistical.bollinger_reversion import BollingerParams
from quantlab.strategies.rule.statistical.itsm import ItsmParams
from quantlab.strategies.rule.statistical.orb import OrbParams
from quantlab.strategies.rule.statistical.reversal import ReversalParams
from quantlab.strategies.rule.statistical.trend import TrendParams
from quantlab.strategies.rule.statistical.vwap_reversion import VwapParams


def _dec(value: Any) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, str | int):
        raise DataError("decimal fields must be strings or integers, never floats")
    try:
        result = Decimal(str(value))
    except InvalidOperation:
        raise DataError("invalid decimal") from None
    if not result.is_finite():
        raise DataError("decimal must be finite")
    return result


def _int(value: Any) -> int:
    if type(value) is not int:
        raise DataError("expected an integer")
    return value


def _bool(value: Any) -> bool:
    if type(value) is not bool:
        raise DataError("expected a boolean")
    return value


def _str(value: Any) -> str:
    if not isinstance(value, str):
        raise DataError("expected a string")
    return value


def _strs(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise DataError("expected a list")
    return tuple(_str(v) for v in value)


def _ints(value: Any) -> tuple[int, ...]:
    if not isinstance(value, list):
        raise DataError("expected a list")
    return tuple(_int(v) for v in value)


def _opt(convert: Any) -> Any:
    return lambda v: None if v is None else convert(v)


_SCALARS: dict[Any, Any] = {Decimal: _dec, int: _int, bool: _bool, str: _str}


def build(cls: Any, raw: Any, convert: dict[str, Any] | None = None) -> Any:
    """Construct a dataclass from a JSON object: unknown keys rejected, fields without a
    default required, scalar types checked exactly."""
    convert = convert or {}
    if not isinstance(raw, dict):
        raise DataError("expected an object")
    spec = {f.name: f for f in fields(cls)}
    required = {n for n, f in spec.items() if f.default is MISSING and f.default_factory is MISSING}
    if set(raw) - set(spec) or required - set(raw):
        raise DataError("unsupported or missing configuration fields")
    out = {}
    for key, value in raw.items():
        conv = convert.get(key) or _SCALARS.get(spec[key].type)
        if conv is None:
            raise DataError("unsupported field type")
        out[key] = conv(value)
    return cls(**out)


def plain(value: Any) -> Any:
    """JSON-ready, canonical view: Decimals as strings, dataclasses as objects."""
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: plain(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, tuple | list):
        return [plain(v) for v in value]
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    return value


@dataclass(frozen=True, slots=True)
class Costs:
    """Explicit, dated-by-the-caller execution costs. Spread and slippage are separate adverse
    offsets from the bar open (each counted once); commission is the venue fee schedule."""

    half_spread_ticks: int
    slippage_ticks: int
    order_latency_seconds: int
    per_unit: Decimal
    min_per_order: Decimal
    max_pct_notional: Decimal | None
    sell_pct_notional: Decimal

    def __post_init__(self) -> None:
        ints = (self.half_spread_ticks, self.slippage_ticks, self.order_latency_seconds)
        decimals = (self.per_unit, self.min_per_order, self.sell_pct_notional)
        if min(ints) < 0 or self.order_latency_seconds > 3600:
            raise DataError("tick offsets and latency cannot be negative; latency <= 1 hour")
        if any(d < 0 for d in decimals) or (self.max_pct_notional or Decimal(0)) < 0:
            raise DataError("fee inputs cannot be negative")


Params = (
    ItsmParams
    | CandlestickParams
    | OrbParams
    | VwapParams
    | BollingerParams
    | ReversalParams
    | TrendParams
)


@dataclass(frozen=True, slots=True)
class StrategySpec:
    name: str
    params: Params
    exit: ExitPolicy


def _protection(raw: Any) -> Protection | None:
    return None if raw is None else build(Protection, raw)


_EXIT = {
    "horizon_seconds": _opt(_int),
    "flatten_lead_seconds": _opt(_int),
    "stop": _protection,
    "target": _protection,
}


def _filters(raw: Any) -> Filters:
    parts = {
        "trend": _opt(lambda v: build(TrendFilter, v)),
        "level": _opt(lambda v: build(LevelFilter, v)),
        "volume": _opt(lambda v: build(VolumeFilter, v)),
        "volatility": _opt(lambda v: build(VolatilityFilter, v, _VOL)),
    }
    result: Filters = build(Filters, raw, parts)
    return result


_VOL = {"min_atr_ticks": _opt(_dec), "max_atr_ticks": _opt(_dec)}


def _splits(raw: Any) -> tuple[tuple[str, Decimal], ...]:
    if not isinstance(raw, list) or any(not isinstance(p, list) or len(p) != 2 for p in raw):
        raise DataError("splits must be [[day, ratio], ...]")
    return tuple((_str(d), _dec(r)) for d, r in raw)


def _itsm(raw: Any) -> tuple[Params, ExitPolicy]:
    params: ItsmParams = build(ItsmParams, raw, {"splits": _splits})
    return params, ExitPolicy()


def _candlestick(raw: Any) -> tuple[Params, ExitPolicy]:
    params: CandlestickParams = build(
        CandlestickParams,
        raw,
        {
            "patterns": _strs,
            "timeframes": _ints,
            "detector": lambda v: build(DetectorConfig, v),
            "filters": _filters,
        },
    )
    return params, ExitPolicy(params.horizon_seconds)


def _orb(raw: Any) -> tuple[Params, ExitPolicy]:
    params: OrbParams = build(
        OrbParams,
        raw,
        {
            "rvol_min": _opt(_dec),
            "breakout_volume_multiple": _opt(_dec),
            "prior_tr_below_atr": _opt(_int),
        },
    )
    return params, ExitPolicy(params.horizon_seconds, exit_on_opposite=False)


def _vwap(raw: Any) -> tuple[Params, ExitPolicy]:
    params: VwapParams = build(VwapParams, raw)
    return params, ExitPolicy(params.horizon_seconds, exit_on_opposite=False)


def _bollinger(raw: Any) -> tuple[Params, ExitPolicy]:
    params: BollingerParams = build(BollingerParams, raw)
    return params, ExitPolicy(params.horizon_seconds, exit_on_opposite=False)


def _reversal(raw: Any) -> tuple[Params, ExitPolicy]:
    params: ReversalParams = build(ReversalParams, raw)
    return params, ExitPolicy(params.horizon_seconds, exit_on_opposite=False)


def _trend(raw: Any) -> tuple[Params, ExitPolicy]:
    params: TrendParams = build(TrendParams, raw)
    return params, ExitPolicy()


_BUILDERS = {
    "itsm": _itsm,
    "candlestick": _candlestick,
    "orb": _orb,
    "vwap_reversion": _vwap,
    "bollinger_reversion": _bollinger,
    "reversal": _reversal,
    "trend": _trend,
}
STRATEGIES = tuple(_BUILDERS)


def _strategy(raw: Any) -> StrategySpec:
    if not isinstance(raw, dict) or set(raw) - {"name", "params", "exit"} or "name" not in raw:
        raise DataError("strategy needs a name and optional params/exit")
    name = _str(raw["name"])
    if name not in _BUILDERS:
        raise DataError("unknown strategy")
    params, default_exit = _BUILDERS[name](raw.get("params", {}))
    exit_policy = build(ExitPolicy, raw["exit"], _EXIT) if "exit" in raw else default_exit
    return StrategySpec(name, params, exit_policy)


@dataclass(frozen=True, slots=True)
class BacktestConfig:
    name: str
    instrument: InstrumentSpec
    capital: Decimal
    data: SyntheticSpec
    costs: Costs
    sizing: Sizing
    risk: RiskLimits
    strategy: StrategySpec

    @classmethod
    def parse(cls, value: Any) -> "BacktestConfig":
        r = exact_fields(
            value,
            {
                "version",
                "name",
                "synthetic",
                "instrument",
                "capital",
                "data",
                "execution",
                "sizing",
                "risk",
                "strategy",
            },
        )
        if r["version"] != 1 or type(r["version"]) is not int or r["synthetic"] is not True:
            raise DataError("only version 1 synthetic backtests are enabled")
        config = cls(
            token(r["name"]),  # printed in reports: no newlines or markup
            build(InstrumentSpec, r["instrument"]),
            _dec(r["capital"]),
            build(
                SyntheticSpec,
                r["data"],
                {"early_close_days": _strs, "holidays": _strs},
            ),
            build(Costs, r["execution"], {"max_pct_notional": _opt(_dec)}),
            build(Sizing, r["sizing"]),
            build(RiskLimits, r["risk"]),
            _strategy(r["strategy"]),
        )
        config.validate()
        return config

    def validate(self) -> None:
        lot = Decimal(self.instrument.lot)
        if self.capital <= 0 or self.capital != round(self.capital, 2):
            raise DataError("capital must be positive and in whole cents")
        if self.sizing.mode == "fixed_quantity" and self.sizing.amount % lot:
            raise DataError("fixed quantity must be a multiple of the lot size")
        latency = self.costs.order_latency_seconds
        lead = self.strategy.exit.flatten_lead_seconds
        if lead is not None and lead <= 60 + latency:
            raise DataError("flatten lead leaves no executable 1-minute bar before the close")
        if self.strategy.params.entry_valid_seconds <= 60 + latency:
            raise DataError("entry validity must exceed order latency plus one bar")

    def payload(self) -> dict[str, Any]:
        result: dict[str, Any] = plain(self)
        return result


def default_config(strategy: str) -> dict[str, Any]:
    """Illustrative synthetic setup. The commission inputs are the IBKR Tiered figures recorded
    in docs/COSTS_AND_PROVIDERS.md (checked 2026-10-30), not a historical schedule."""
    if strategy not in STRATEGIES:
        raise DataError("unknown strategy")
    params: dict[str, Any] = (
        {"patterns": ["bullish_engulfing", "bearish_engulfing", "hammer", "shooting_star"]}
        | {"timeframes": [5], "horizon_seconds": 1800}
        if strategy == "candlestick"
        else {}  # every other demo uses the documented parameter defaults
    )
    entries = {"itsm": 1, "orb": 1, "candlestick": 5, "reversal": 8}.get(strategy, 3)
    return {
        "version": 1,
        "name": f"{strategy}-synthetic-demo",
        "synthetic": True,
        "instrument": {
            "symbol": "SYNTH",
            "venue": "XNAS",
            "kind": "equity",
            "currency": "USD",
            "tick": "0.01",
            "multiplier": 1,
            "lot": 1,
        },
        "capital": "100000",
        "data": {
            "seed": 7,
            "start_day": "2022-03-07",
            "sessions": 30,
            "open_price": "100.00",
            "step_ticks": 4,
            "wick_ticks": 2,
            "gap_ticks": 60,
            "volume": 1000,
            "delay_seconds": 1,
            "early_close_days": [],
            "holidays": [],
        },
        "execution": {
            "half_spread_ticks": 1,
            "slippage_ticks": 0,
            "order_latency_seconds": 0,
            "per_unit": "0.0035",
            "min_per_order": "0.35",
            "max_pct_notional": "0.01",
            "sell_pct_notional": "0.0000206",
        },
        "sizing": {"mode": "fixed_quantity", "amount": "100"},
        "risk": {
            "max_quantity": "500",
            "max_notional": "50000",
            "max_leverage": "1",
            "max_entries_per_session": entries,
            "max_session_loss": "1000",
            "max_data_age_seconds": 180,
        },
        "strategy": {"name": strategy, "params": params},
    }
