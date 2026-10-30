"""Optional causal confirmations for candlestick signals (trend, level, volume, volatility).

An enabled filter must pass; a disabled one adds nothing. Every estimator is trailing: it sees
only completed candles that ended before the pattern began, and insufficient history fails
closed with a stable reason code.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from quantlab.data.model import DataError
from quantlab.strategies.market import Candle


@dataclass(frozen=True, slots=True)
class TrendFilter:
    lookback: int
    long_requires: str = "down"  # trend before the pattern: "up" | "down" | "any"
    short_requires: str = "up"


@dataclass(frozen=True, slots=True)
class LevelFilter:
    lookback: int
    tolerance_ticks: int


@dataclass(frozen=True, slots=True)
class VolumeFilter:
    lookback: int
    min_multiple: Decimal


@dataclass(frozen=True, slots=True)
class VolatilityFilter:
    lookback: int
    min_atr_ticks: Decimal | None = None
    max_atr_ticks: Decimal | None = None


@dataclass(frozen=True, slots=True)
class Filters:
    """Optional confirmations; an enabled filter must pass, a disabled one adds nothing."""

    trend: TrendFilter | None = None
    level: LevelFilter | None = None
    volume: VolumeFilter | None = None
    volatility: VolatilityFilter | None = None

    def __post_init__(self) -> None:
        lookbacks = [
            f.lookback for f in (self.trend, self.level, self.volume, self.volatility) if f
        ]
        if any(type(n) is not int or n < 1 for n in lookbacks):
            raise DataError("filter lookbacks must be positive integers")
        if self.trend and not {self.trend.long_requires, self.trend.short_requires} <= {
            "up",
            "down",
            "any",
        }:
            raise DataError("unsupported trend requirement")
        if self.volume and self.volume.min_multiple <= 0:
            raise DataError("volume multiple must be positive")
        if self.level and self.level.tolerance_ticks < 0:
            raise DataError("level tolerance cannot be negative")

    @property
    def max_lookback(self) -> int:
        enabled = [f.lookback for f in (self.trend, self.level, self.volume, self.volatility) if f]
        return max(enabled, default=0) + 1


def evaluate_filters(
    filters: Filters,
    direction: str,
    pattern: Sequence[Candle],
    prior: Sequence[Candle],
    tick: Decimal,
) -> str | None:
    """None when every enabled filter passes, else a stable reason code.

    `prior` holds only completed candles that ended before the pattern began, so each
    estimator is trailing; insufficient history fails closed as `filter_warmup:<name>`.
    """
    if filters.trend:
        t = filters.trend
        if len(prior) < t.lookback:
            return "filter_warmup:trend"
        recent = prior[-t.lookback :]
        mean = sum((k.close for k in recent), Decimal(0)) / t.lookback
        state = "up" if recent[-1].close > mean else "down" if recent[-1].close < mean else "flat"
        need = t.long_requires if direction == "long" else t.short_requires
        if need != "any" and state != need:
            return "filter_failed:trend"
    if filters.level:
        lv = filters.level
        if len(prior) < lv.lookback:
            return "filter_warmup:level"
        recent = prior[-lv.lookback :]
        slack = lv.tolerance_ticks * tick
        if direction == "long" and min(k.low for k in pattern) > min(k.low for k in recent) + slack:
            return "filter_failed:level"
        if direction == "short" and max(k.high for k in pattern) < (
            max(k.high for k in recent) - slack
        ):
            return "filter_failed:level"
    if filters.volume:
        v = filters.volume
        if len(prior) < v.lookback:
            return "filter_warmup:volume"
        volumes = [k.volume for k in prior[-v.lookback :]]
        if any(x <= 0 for x in volumes) or pattern[-1].volume <= 0:
            return "filter_unavailable:volume"
        if pattern[-1].volume < v.min_multiple * Decimal(sum(volumes)) / len(volumes):
            return "filter_failed:volume"
    if filters.volatility:
        vo = filters.volatility
        if len(prior) < vo.lookback + 1:
            return "filter_warmup:volatility"
        recent = prior[-(vo.lookback + 1) :]
        true_ranges = [
            max(b.high - b.low, abs(b.high - a.close), abs(b.low - a.close))
            for a, b in zip(recent, recent[1:], strict=False)
        ]
        atr = sum(true_ranges, Decimal(0)) / vo.lookback
        if vo.min_atr_ticks is not None and atr < vo.min_atr_ticks * tick:
            return "filter_failed:volatility"
        if vo.max_atr_ticks is not None and atr > vo.max_atr_ticks * tick:
            return "filter_failed:volatility"
    return None
