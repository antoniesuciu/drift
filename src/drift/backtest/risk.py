"""Shared sizing, deterministic risk limits and exit policy, independent of any strategy.

Strategies only propose a direction. Quantity comes from `Sizing`, every entry must pass
`RiskLimits.check_entry`, and positions are closed by `ExitPolicy`. Limits have no defaults:
an absent or non-positive limit is a configuration error, so nothing trades unlimited.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from drift.data.model import SECOND, DataError

_SIZING_MODES = ("fixed_quantity", "target_notional", "equity_fraction")


@dataclass(frozen=True, slots=True)
class Sizing:
    """`fixed_quantity`: amount in units. `target_notional`: amount in account currency.
    `equity_fraction`: amount as a fraction (0, 1] of the balance at the decision, so a virtual
    portfolio compounds and shrinks with its own capital."""

    mode: str
    amount: Decimal

    def __post_init__(self) -> None:
        if self.mode not in _SIZING_MODES or self.amount <= 0:
            raise DataError("sizing needs a known mode and a positive amount")
        if self.mode == "equity_fraction" and self.amount > 1:
            raise DataError("an equity fraction cannot exceed 1")

    def quantity(
        self, price: Decimal, multiplier: Decimal, lot: Decimal, balance: Decimal = Decimal(0)
    ) -> Decimal:
        """Whole lots, rounded down; zero when the target does not afford one lot."""
        if self.mode == "fixed_quantity":
            raw = self.amount
        elif self.mode == "target_notional":
            raw = self.amount / (price * multiplier)
        else:
            raw = self.amount * balance / (price * multiplier)
        return (raw // lot) * lot


@dataclass(frozen=True, slots=True)
class RiskLimits:
    max_quantity: Decimal
    max_notional: Decimal
    max_leverage: Decimal
    max_entries_per_session: int
    max_session_loss: Decimal
    max_data_age_seconds: int

    def __post_init__(self) -> None:
        values = (
            self.max_quantity,
            self.max_notional,
            self.max_leverage,
            self.max_entries_per_session,
            self.max_session_loss,
            self.max_data_age_seconds,
        )
        if any(v <= 0 for v in values):
            raise DataError("every risk limit must be explicit and positive")

    def check_entry(
        self,
        *,
        quantity: Decimal,
        price: Decimal,
        multiplier: Decimal,
        balance: Decimal,
        data_age_ns: int,
        entries_today: int,
        loss_today: Decimal,
    ) -> tuple[str, ...]:
        """Stable reason codes; an empty tuple means the entry is authorized."""
        notional = quantity * price * multiplier
        checks = (
            (quantity <= 0, "quantity_below_lot"),
            (quantity > self.max_quantity, "quantity_exceeds_limit"),
            (notional > self.max_notional, "notional_exceeds_limit"),
            (balance <= 0 or notional > self.max_leverage * balance, "leverage_exceeds_limit"),
            (data_age_ns > self.max_data_age_seconds * SECOND, "stale_data"),
            (entries_today >= self.max_entries_per_session, "session_entry_limit_reached"),
            (loss_today >= self.max_session_loss, "session_loss_limit_reached"),
        )
        return tuple(code for failed, code in checks if failed)


@dataclass(frozen=True, slots=True)
class Protection:
    """Stop-loss or take-profit distance from the entry fill, in ticks or percent of price."""

    kind: str
    value: Decimal

    def __post_init__(self) -> None:
        if self.kind not in ("ticks", "percent") or self.value <= 0:
            raise DataError("protection needs kind ticks|percent and a positive value")

    def distance(self, entry: Decimal, tick: Decimal) -> Decimal:
        raw = self.value * tick if self.kind == "ticks" else entry * self.value / 100
        return max((raw / tick).quantize(Decimal(1), rounding=ROUND_HALF_UP), Decimal(1)) * tick


@dataclass(frozen=True, slots=True)
class ExitPolicy:
    """Every position needs a time exit. Stops and targets are optional and evaluated on
    completed bars: when a bar's range reaches a level the exit is decided at that bar's
    availability and filled at the next eligible open, so gaps and delay are paid for, and
    when one bar touches both levels the stop wins (conservative, never the profitable order).
    """

    horizon_seconds: int | None = None
    flatten_lead_seconds: int | None = 120
    stop: Protection | None = None
    target: Protection | None = None
    exit_on_opposite: bool = True

    def __post_init__(self) -> None:
        if self.horizon_seconds is None and self.flatten_lead_seconds is None:
            raise DataError("an exit policy needs a horizon or a session flatten lead")
        for v in (self.horizon_seconds, self.flatten_lead_seconds):
            if v is not None and v < 1:
                raise DataError("exit times must be positive seconds")

    def levels(
        self, side: int, entry: Decimal, tick: Decimal
    ) -> tuple[Decimal | None, Decimal | None]:
        """(stop, target) prices for side +1 long / -1 short, on the tick grid."""
        stop = target = None
        if self.stop:
            stop = entry - side * self.stop.distance(entry, tick)
        if self.target:
            target = entry + side * self.target.distance(entry, tick)
        if stop is not None and stop <= 0:
            raise DataError("stop level would not be positive")
        return stop, target
