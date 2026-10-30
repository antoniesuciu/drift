"""Candlestick recognition (docs/STRATEGIES.md): completed candles in, observations out.

Detection is separate from trading policy: nothing here knows about orders, positions or an
engine, and the output is reusable as ML features. Prices are `Decimal`, comparisons are exact,
and thresholds are dimensionless ratios or tick counts from configuration, never instrument
constants.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, fields
from decimal import Decimal

from quantlab.data.model import DataError, canonical, digest
from quantlab.strategies.market import Candle

DETECTOR_VERSION = "CAND-DET-v1"
_COLORS = ("any", "bullish", "bearish")


@dataclass(frozen=True, slots=True)
class DetectorConfig:
    """Frozen recognition parameters. Defaults are textbook starting points, version-tagged
    research choices that must be fixed before results; they are not tuned or validated."""

    inclusive: bool = True  # edge equality counts as satisfying a comparison
    require_gap: bool = False  # morning/evening star only; False suits continuous sessions
    doji_max_body_ratio: Decimal = Decimal("0.10")
    small_body_max_ratio: Decimal = Decimal("0.30")
    long_body_min_ratio: Decimal = Decimal("0.60")
    wick_min_body_multiple: Decimal = Decimal("2")
    opposite_wick_max_range_ratio: Decimal = Decimal("0.10")
    star_penetration: Decimal = Decimal("0.50")
    soldier_max_wick_ratio: Decimal = Decimal("0.25")
    single_color: str = "any"  # hammer / shooting-star candle color condition

    def __post_init__(self) -> None:
        ratios = (
            self.doji_max_body_ratio,
            self.small_body_max_ratio,
            self.long_body_min_ratio,
            self.opposite_wick_max_range_ratio,
            self.soldier_max_wick_ratio,
        )
        if not all(Decimal(0) <= r <= Decimal(1) for r in ratios):
            raise DataError("detector ratios must lie in [0, 1]")
        if not Decimal(0) < self.star_penetration <= Decimal(1):
            raise DataError("star penetration must lie in (0, 1]")
        if self.wick_min_body_multiple <= 0 or self.single_color not in _COLORS:
            raise DataError("invalid wick multiple or color condition")
        if self.small_body_max_ratio >= self.long_body_min_ratio:
            raise DataError("small-body ratio must be below the long-body ratio")

    def params_hash(self) -> str:
        return digest(canonical({f.name: str(getattr(self, f.name)) for f in fields(self)}))


@dataclass(frozen=True, slots=True)
class Detection:
    """A pattern observation: provenance and shape attributes, no direction policy."""

    pattern: str
    direction: str  # "long" | "short" | "neutral": the pattern's own definition
    start: int
    end: int
    day: str
    available: int
    ref_high: Decimal
    ref_low: Decimal
    attrs: tuple[tuple[str, str], ...]
    params_hash: str
    version: str = DETECTOR_VERSION


def _le(c: DetectorConfig, a: Decimal, b: Decimal) -> bool:
    return a <= b if c.inclusive else a < b


def _contained(c: DetectorConfig, point: Decimal, low: Decimal, high: Decimal) -> bool:
    return _le(c, low, point) and _le(c, point, high)


def _engulfs(c: DetectorConfig, first: Candle, second: Candle) -> bool:
    lo, hi = min(first.open, first.close), max(first.open, first.close)
    return _le(c, min(second.open, second.close), lo) and _le(c, hi, max(second.open, second.close))


def bullish_engulfing(c: DetectorConfig, w: Sequence[Candle]) -> bool:
    return w[0].bearish and w[1].bullish and _engulfs(c, w[0], w[1])


def bearish_engulfing(c: DetectorConfig, w: Sequence[Candle]) -> bool:
    return w[0].bullish and w[1].bearish and _engulfs(c, w[0], w[1])


def _color_ok(c: DetectorConfig, k: Candle) -> bool:
    return c.single_color == "any" or (k.bullish if c.single_color == "bullish" else k.bearish)


def hammer(c: DetectorConfig, w: Sequence[Candle]) -> bool:
    k = w[0]
    return (
        k.range > 0
        and k.body > 0
        and _color_ok(c, k)
        and _le(c, k.body, c.small_body_max_ratio * k.range)
        and _le(c, c.wick_min_body_multiple * k.body, k.lower)
        and _le(c, k.upper, c.opposite_wick_max_range_ratio * k.range)
    )


def shooting_star(c: DetectorConfig, w: Sequence[Candle]) -> bool:
    k = w[0]
    return (
        k.range > 0
        and k.body > 0
        and _color_ok(c, k)
        and _le(c, k.body, c.small_body_max_ratio * k.range)
        and _le(c, c.wick_min_body_multiple * k.body, k.upper)
        and _le(c, k.lower, c.opposite_wick_max_range_ratio * k.range)
    )


def _star(c: DetectorConfig, w: Sequence[Candle], bullish: bool) -> bool:
    first, mid, last = w
    if first.range <= 0 or mid.range <= 0:
        return False  # ratio-dependent detection withheld on degenerate candles
    right = (first.bearish and last.bullish) if bullish else (first.bullish and last.bearish)
    if not right or not _le(c, c.long_body_min_ratio * first.range, first.body):
        return False
    if not _le(c, mid.body, c.small_body_max_ratio * mid.range):
        return False
    depth = c.star_penetration * first.body
    if bullish:
        if not _le(c, first.close + depth, last.close):
            return False
        return not c.require_gap or max(mid.open, mid.close) < first.close
    if not _le(c, last.close, first.close - depth):
        return False
    return not c.require_gap or min(mid.open, mid.close) > first.close


def morning_star(c: DetectorConfig, w: Sequence[Candle]) -> bool:
    return _star(c, w, True)


def evening_star(c: DetectorConfig, w: Sequence[Candle]) -> bool:
    return _star(c, w, False)


def _three(c: DetectorConfig, w: Sequence[Candle], up: bool) -> bool:
    for k in w:
        wick = k.upper if up else k.lower
        if k.range <= 0 or not (k.bullish if up else k.bearish):
            return False
        if not _le(c, c.long_body_min_ratio * k.range, k.body):
            return False
        if not _le(c, wick, c.soldier_max_wick_ratio * k.range):
            return False
    for a, b in zip(w, w[1:], strict=False):
        if (b.close <= a.close) if up else (b.close >= a.close):
            return False
        if not _contained(c, b.open, min(a.open, a.close), max(a.open, a.close)):
            return False
    return True


def three_white_soldiers(c: DetectorConfig, w: Sequence[Candle]) -> bool:
    return _three(c, w, True)


def three_black_crows(c: DetectorConfig, w: Sequence[Candle]) -> bool:
    return _three(c, w, False)


def inside_bar(c: DetectorConfig, w: Sequence[Candle]) -> bool:
    return _le(c, w[0].low, w[1].low) and _le(c, w[1].high, w[0].high)


def doji(c: DetectorConfig, w: Sequence[Candle]) -> bool:
    k = w[0]
    return k.range > 0 and _le(c, k.body, c.doji_max_body_ratio * k.range)


# id -> (candles needed, direction implied by the pattern's own definition, predicate)
PATTERNS: dict[str, tuple[int, str, Callable[[DetectorConfig, Sequence[Candle]], bool]]] = {
    "bullish_engulfing": (2, "long", bullish_engulfing),
    "bearish_engulfing": (2, "short", bearish_engulfing),
    "hammer": (1, "long", hammer),
    "shooting_star": (1, "short", shooting_star),
    "morning_star": (3, "long", morning_star),
    "evening_star": (3, "short", evening_star),
    "doji": (1, "neutral", doji),
    "three_white_soldiers": (3, "long", three_white_soldiers),
    "three_black_crows": (3, "short", three_black_crows),
    "inside_bar": (2, "neutral", inside_bar),
}


def contiguous(window: Sequence[Candle], span_sessions: bool) -> bool:
    """Consecutive candles with no unclassified gap; sessions may not be bridged by default."""
    return all(
        a.end == b.start and (span_sessions or a.day == b.day)
        for a, b in zip(window, window[1:], strict=False)
    )


def detect(
    config: DetectorConfig,
    history: Sequence[Candle],
    patterns: Sequence[str],
    span_sessions: bool = False,
) -> list[Detection]:
    """Patterns whose final candle is `history[-1]`; deterministic order by pattern id."""
    found = []
    for name in sorted(patterns):
        if name not in PATTERNS:
            raise DataError("unknown detection id")
        span, direction, predicate = PATTERNS[name]
        if len(history) < span:
            continue
        window = tuple(history[-span:])
        if not contiguous(window, span_sessions) or not predicate(config, window):
            continue
        ref = window[0] if name == "inside_bar" else window[-1]
        last = window[-1]
        attrs: list[tuple[str, str]] = []
        if last.range > 0:
            attrs = [
                ("body_ratio", str(last.body / last.range)),
                ("lower_wick_ratio", str(last.lower / last.range)),
                ("upper_wick_ratio", str(last.upper / last.range)),
            ]
        found.append(
            Detection(
                name,
                direction,
                window[0].start,
                last.end,
                last.day,
                max(k.available for k in window),
                ref.high,
                ref.low,
                tuple(attrs),
                config.params_hash(),
            )
        )
    return found
