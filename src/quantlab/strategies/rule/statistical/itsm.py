"""EXP-001 intraday time-series momentum (M3a): sign agreement of two completed-candle returns.

Pure function of the candles pushed so far: a rule never sees the future, an order, a position
or a broker. `on_candle` returns at most one `Proposal` per session.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from quantlab.data.model import SECOND, DataError, local_ns
from quantlab.strategies.calendar import MINUTE_NS, Calendar
from quantlab.strategies.market import Candle
from quantlab.strategies.proposal import Intent, Proposal
from quantlab.strategies.rule.statistical.session import check_clock

ITSM_VERSION = "EXP-001-NVDA-v1"


@dataclass(frozen=True, slots=True)
class ItsmParams:
    """EXP-001 sign-agreement rule. Endpoints are closes of the minute *ending* at the clock."""

    early_end: str = "10:00"
    preclose_start: str = "15:00"
    decision: str = "15:30"
    allow_short: bool = True
    entry_valid_seconds: int = 300
    # (effective trade date, share ratio): a 4:1 split is ("2021-07-20", "4")
    splits: tuple[tuple[str, Decimal], ...] = ()

    def __post_init__(self) -> None:
        for clock in (self.early_end, self.preclose_start, self.decision):
            check_clock(clock)
        if not self.early_end < self.preclose_start < self.decision:
            raise DataError("endpoints must satisfy open < early < preclose start < decision")
        if self.entry_valid_seconds < 1:
            raise DataError("entry validity must be positive")
        if any(ratio <= 0 for _, ratio in self.splits):
            raise DataError("split ratios must be positive")
        for day, _ in self.splits:  # a malformed date would silently never apply
            date.fromisoformat(day)


@dataclass(slots=True)
class ItsmRule:
    """previous-close -> early_end and preclose_start -> decision sign agreement.

    Abstains (NO_TRADE with a reason) on early/closed sessions, an early-closing previous
    session, missing endpoints or any unknown minute before the decision. At most one
    proposal per session, issued when the decision candle becomes available.
    """

    params: ItsmParams
    instrument_id: str
    calendar: Calendar
    agent_id: str = "itsm-001"
    strategy_id: str = "EXP-001-ITSM"
    _closes: dict[int, tuple[Decimal, int]] = field(default_factory=dict)
    _ends: dict[str, set[int]] = field(default_factory=dict)
    _done: set[str] = field(default_factory=set)

    def _endpoints(self, day: str) -> dict[str, int]:
        p = self.params
        return {
            "early": local_ns(day, p.early_end),
            "preclose_start": local_ns(day, p.preclose_start),
            "decision": local_ns(day, p.decision),
        }

    def on_candle(self, c: Candle) -> Proposal | None:
        session = self.calendar.get(c.day)
        if session is None:
            return None
        ends = self._ends.setdefault(c.day, set())
        ends.add(c.end)
        previous = self.calendar.previous(c.day)
        points = self._endpoints(c.day)
        if c.end in points.values() or (c.end == session.close):
            self._closes[c.end] = (c.close, c.volume)
        trigger = points["decision"] if session.full else session.close
        if c.end != trigger or c.day in self._done:
            return None
        self._done.add(c.day)

        reasons: list[str] = []
        if not session.full:
            return self._abstain(c, ("early_close",), session.close)
        if previous is None:
            reasons.append("previous_session_unknown")
        elif not previous.full:
            reasons.append("previous_early_close")
        expected = range(session.open + MINUTE_NS, c.end + 1, MINUTE_NS)
        if any(e not in ends for e in expected):
            reasons.append("unknown_gap_before_decision")

        def close(name: str, end: int | None) -> Decimal | None:
            row = self._closes.get(end) if end is not None else None
            if row is None or row[1] <= 0:
                reasons.append(f"unavailable:{name}")
                return None
            return row[0]

        base = close("previous_close", previous.close if previous else None)
        early = close("early", points["early"])
        start = close("preclose_start", points["preclose_start"])
        last = close("decision", points["decision"])
        intent, rationale = Intent.NO_TRADE, "abstain"
        if not reasons and base and early and start and last:
            ratio = next((r for d, r in self.params.splits if d == c.day), Decimal(1))
            r_early = early / (base / ratio) - 1
            r_pre = last / start - 1
            rationale = f"r_early={r_early} r_preclose={r_pre} split_ratio={ratio}"
            if r_early > 0 and r_pre > 0:
                intent = Intent.LONG
            elif r_early < 0 and r_pre < 0:
                if self.params.allow_short:
                    intent = Intent.SHORT
                else:
                    reasons.append("short_disabled")
            else:
                reasons.append("zero_or_disagreement")
        return self._proposal(c, intent, rationale, tuple(sorted(set(reasons))), session.close)

    def _abstain(self, c: Candle, reasons: tuple[str, ...], close: int) -> Proposal:
        return self._proposal(c, Intent.NO_TRADE, "abstain", reasons, close)

    def _proposal(
        self, c: Candle, intent: Intent, rationale: str, reasons: tuple[str, ...], close: int
    ) -> Proposal:
        return Proposal(
            f"{self.strategy_id}|{self.instrument_id}|{c.day}|{c.available}",
            self.agent_id,
            self.strategy_id,
            self.instrument_id,
            c.available,
            c.available,
            c.available + self.params.entry_valid_seconds * SECOND,
            max(close - c.available, 0) // SECOND,
            intent,
            ITSM_VERSION,
            (f"session:{c.day}", f"decision_end:{c.end}"),
            rationale,
            reasons,
        )
