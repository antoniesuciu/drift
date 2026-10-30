"""Execute any strategy through NautilusTrader and collect the results.

Matching, commissions, positions and account balances come from the Nautilus engine; this
module only feeds it data, translates approved proposals into market orders and records what
the engine reports. Timing contract (no retrospective fills):

* the strategy sees a candle at its `available` time (bar `ts_init`);
* each bar's open is also published as a quote at the bar *start*, carrying the configured
  half-spread and slippage, and `bar_execution` is off so only these quotes drive matching;
* an order decided at time D is submitted on the first quote strictly after D plus the order
  latency, and fills at that quote: the open of the first bar starting after the decision.
"""

import platform
from dataclasses import dataclass, field
from decimal import Decimal
from importlib.metadata import version
from pathlib import Path
from typing import Any

from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.backtest.models import FeeModel, FillModel
from nautilus_trader.config import BacktestEngineConfig, LoggingConfig
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.data import Bar, BarType, QuoteTick
from nautilus_trader.model.enums import AccountType, AssetClass, OmsType, OrderSide, TimeInForce
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.instruments import Equity, FuturesContract
from nautilus_trader.model.objects import Money, Price, Quantity
from nautilus_trader.trading.config import StrategyConfig
from nautilus_trader.trading.strategy import Strategy

from quantlab import __version__
from quantlab.backtest.config import BacktestConfig, Costs
from quantlab.backtest.data import InstrumentSpec, MarketData, generate
from quantlab.backtest.report import BacktestResult, Trade, metrics
from quantlab.backtest.risk import ExitPolicy, RiskLimits, Sizing
from quantlab.data.model import SECOND, TZ_VERSION, DataError, canonical, digest
from quantlab.strategies.base import Agent
from quantlab.strategies.calendar import MINUTE_NS, Calendar
from quantlab.strategies.market import Candle
from quantlab.strategies.proposal import Intent, Proposal
from quantlab.strategies.rule.candlestick.policy import CandlestickParams, CandlestickRule
from quantlab.strategies.rule.statistical.bollinger_reversion import (
    BollingerParams,
    BollingerReversionRule,
)
from quantlab.strategies.rule.statistical.itsm import ItsmParams, ItsmRule
from quantlab.strategies.rule.statistical.orb import OrbParams, OrbRule
from quantlab.strategies.rule.statistical.reversal import ReversalParams, ReversalRule
from quantlab.strategies.rule.statistical.trend import TrendParams, TrendRule
from quantlab.strategies.rule.statistical.vwap_reversion import VwapParams, VwapReversionRule

_NEVER = 2**63 - 1


def make_instrument(spec: InstrumentSpec) -> Equity | FuturesContract:
    iid = InstrumentId.from_str(spec.id)
    common: dict[str, Any] = {
        "instrument_id": iid,
        "raw_symbol": Symbol(spec.symbol),
        "currency": USD,
        "price_precision": spec.precision,
        "price_increment": Price.from_str(str(spec.tick)),
        "lot_size": Quantity.from_int(spec.lot),
        "ts_event": 0,
        "ts_init": 0,
    }
    if spec.kind == "equity":
        return Equity(**common)
    return FuturesContract(
        **common,
        asset_class=AssetClass.INDEX,
        multiplier=Quantity.from_int(spec.multiplier),
        underlying=spec.symbol,
        activation_ns=0,
        expiration_ns=4_102_444_800 * SECOND,
    )


def make_agent(config: BacktestConfig, calendar: Calendar) -> Agent:
    params = config.strategy.params
    iid = config.instrument.id
    if isinstance(params, ItsmParams):
        return ItsmRule(params, iid, calendar)
    if isinstance(params, CandlestickParams):
        return CandlestickRule(params, iid, config.instrument.tick, calendar)
    if isinstance(params, OrbParams):
        return OrbRule(params, iid, calendar)
    if isinstance(params, VwapParams):
        return VwapReversionRule(params, iid, calendar)
    if isinstance(params, BollingerParams):
        return BollingerReversionRule(params, iid, calendar)
    if isinstance(params, ReversalParams):
        return ReversalRule(params, iid, calendar)
    if isinstance(params, TrendParams):
        return TrendRule(params, iid, calendar)
    raise DataError("unknown strategy")


class ConfiguredFees(FeeModel):
    """Per-unit commission with a per-order minimum and cap, plus a sell-side regulatory rate."""

    def __init__(self, costs: Costs) -> None:
        super().__init__()
        self._c = costs

    def get_commission(self, order: Any, fill_qty: Any, fill_px: Any, instrument: Any) -> Money:
        c = self._c
        qty = fill_qty.as_decimal()
        notional = qty * fill_px.as_decimal() * instrument.multiplier.as_decimal()
        fee = max(c.per_unit * qty, c.min_per_order)
        if c.max_pct_notional is not None:
            fee = min(fee, c.max_pct_notional * notional)
        if order.side == OrderSide.SELL:
            fee += c.sell_pct_notional * notional
        return Money(fee, instrument.quote_currency)


@dataclass(slots=True)
class _Order:
    """A decision waiting for an executable quote."""

    kind: str  # "entry" | "exit"
    side: int  # +1 buy, -1 sell
    reason: str
    proposal: Proposal | None
    eligible_after: int
    valid_until: int


@dataclass(slots=True)
class _Inflight:
    kind: str
    side: int
    quantity: Decimal
    reason: str
    proposal_id: str


@dataclass(slots=True)
class _Open:
    side: int
    quantity: Decimal
    entry_ts: int
    entry_price: Decimal
    entry_commission: Decimal
    proposal_id: str
    signal: str
    session_close: int
    schedule: list[tuple[int, str]]
    stop: Decimal | None
    target: Decimal | None
    flags: list[str] = field(default_factory=list)


class RuleStrategy(Strategy):
    """Runs one agent: proposal -> sizing -> risk -> market order, exits per `ExitPolicy`."""

    def __init__(
        self,
        agent: Agent,
        policy: ExitPolicy,
        sizing: Sizing,
        limits: RiskLimits,
        spec: InstrumentSpec,
        calendar: Calendar,
        latency_ns: int,
    ) -> None:
        super().__init__(StrategyConfig(strategy_id="RULE-001", order_id_tag="001"))
        self._agent, self._policy, self._sizing, self._limits = agent, policy, sizing, limits
        self._spec, self._calendar, self._latency = spec, calendar, latency_ns
        self._iid = InstrumentId.from_str(spec.id)
        self._venue = Venue(spec.venue)
        self._bar_type = BarType.from_str(f"{spec.id}-1-MINUTE-LAST-EXTERNAL")
        self._multiplier = Decimal(spec.multiplier)
        self._lot = Decimal(spec.lot)
        self._pending: _Order | None = None
        self._inflight: _Inflight | None = None
        self._open: _Open | None = None
        self._consumed: set[str] = set()
        self._entries: dict[str, int] = {}
        self._pnl: dict[str, Decimal] = {}
        self._records: dict[str, dict[str, Any]] = {}
        self.proposals: list[dict[str, Any]] = []
        self.rejections: list[dict[str, Any]] = []
        self.trades: list[Trade] = []

    # ---- engine callbacks -------------------------------------------------------------
    def on_start(self) -> None:
        self.subscribe_bars(self._bar_type)
        self.subscribe_quote_ticks(self._iid)

    def on_bar(self, bar: Bar) -> None:
        candle = self._candle(bar)
        self._check_protection(candle)
        proposal = self._agent.on_candle(candle)
        if proposal is not None:
            self._handle(proposal, candle)

    def on_quote_tick(self, tick: QuoteTick) -> None:
        if self._inflight is not None:
            return
        ts = tick.ts_event
        held = self._open
        if held is not None:
            if ts > held.session_close:  # survived its session: flatten at once, flagged
                held.flags.append("missed_cutoff")
                self._exit("missed_cutoff_forced")
                return
            if self._pending is None:
                due = sorted((t, r) for t, r in held.schedule if ts > t + self._latency)
                if due:
                    self._exit(due[0][1])
                    return
        order = self._pending
        if order is None:
            return
        if ts > order.valid_until:
            self._pending = None
            self._status(order.proposal, "expired_unfilled")
        elif ts > order.eligible_after:
            self._pending = None
            if order.kind == "exit":
                self._exit(order.reason)
            else:
                mid = (Decimal(str(tick.bid_price)) + Decimal(str(tick.ask_price))) / 2
                self._enter(order, ts, mid)

    def on_order_filled(self, event: Any) -> None:
        flight = self._inflight
        if flight is None:
            raise DataError("fill without an order in flight")
        price = Decimal(str(event.last_px))
        quantity = event.last_qty.as_decimal()
        commission = event.commission.as_decimal()
        if quantity != flight.quantity:
            raise DataError("partial fills are not modeled")
        self._inflight = None
        ts = event.ts_event
        if flight.kind == "entry":
            session = self._calendar.containing(ts)
            if session is None:
                raise DataError("fill outside the calendar")
            schedule: list[tuple[int, str]] = []
            if self._policy.horizon_seconds is not None:
                schedule.append((ts + self._policy.horizon_seconds * SECOND, "horizon"))
            if self._policy.flatten_lead_seconds is not None:
                lead = self._policy.flatten_lead_seconds * SECOND
                schedule.append((session.close - lead, "session_flatten"))
            stop, target = self._policy.levels(flight.side, price, self._spec.tick)
            self._open = _Open(
                flight.side,
                quantity,
                ts,
                price,
                commission,
                flight.proposal_id,
                flight.reason,
                session.close,
                schedule,
                stop,
                target,
            )
            self._status_id(flight.proposal_id, "filled")
            return
        held = self._open
        if held is None:
            raise DataError("exit fill without an open position")
        gross = held.side * (price - held.entry_price) * held.quantity * self._multiplier
        fees = held.entry_commission + commission
        trade = Trade(
            len(self.trades) + 1,
            "LONG" if held.side > 0 else "SHORT",
            held.quantity,
            held.entry_ts,
            ts,
            held.entry_price,
            price,
            gross,
            fees,
            gross - fees,
            flight.reason,
            held.signal,
            held.proposal_id,
            tuple(held.flags),
        )
        self.trades.append(trade)
        session = self._calendar.containing(ts)
        if session is not None:
            self._pnl[session.day] = self._pnl.get(session.day, Decimal(0)) + trade.net_pnl
        self._open = None

    def on_order_denied(self, event: Any) -> None:
        self._engine_reject(event)

    def on_order_rejected(self, event: Any) -> None:
        self._engine_reject(event)

    # ---- decisions --------------------------------------------------------------------
    def _candle(self, bar: Bar) -> Candle:
        start = bar.ts_event - MINUTE_NS
        session = self._calendar.containing(start)
        if session is None:
            raise DataError("bar outside the calendar")
        return Candle(
            start,
            bar.ts_event,
            bar.ts_init,
            Decimal(str(bar.open)),
            Decimal(str(bar.high)),
            Decimal(str(bar.low)),
            Decimal(str(bar.close)),
            int(bar.volume.as_decimal()),
            session.day,
        )

    def _check_protection(self, candle: Candle) -> None:
        held = self._open
        if held is None or self._pending is not None or self._inflight is not None:
            return
        if candle.start < held.entry_ts:
            return
        long_ = held.side > 0
        stop_hit = held.stop is not None and (
            candle.low <= held.stop if long_ else candle.high >= held.stop
        )
        target_hit = held.target is not None and (
            candle.high >= held.target if long_ else candle.low <= held.target
        )
        if not (stop_hit or target_hit):
            return
        if stop_hit and target_hit:
            held.flags.append("stop_and_target_same_bar")
        reason = "stop_loss" if stop_hit else "take_profit"
        self._pending = _Order(
            "exit", -held.side, reason, None, candle.available + self._latency, _NEVER
        )

    def _handle(self, p: Proposal, candle: Candle) -> None:
        record: dict[str, Any] = {
            "proposal_id": p.proposal_id,
            "generated_at": p.generated_at,
            "intent": str(p.intent),
            "reasons": list(p.reasons),
            "rationale": p.rationale,
            "status": "no_trade",
        }
        self.proposals.append(record)
        self._records[p.proposal_id] = record
        if p.intent == Intent.NO_TRADE:
            return
        if p.proposal_id in self._consumed:
            record["status"] = "rejected:duplicate_proposal"
            return
        self._consumed.add(p.proposal_id)
        if not p.live_at(candle.available):
            record["status"] = "rejected:expired"
            return
        busy = self._pending is not None or self._inflight is not None
        held = self._open
        if held is not None:
            # FLAT is the opposite signal of an agent with the other side disabled
            opposite = p.intent == Intent.FLAT or (p.intent == Intent.LONG) != (held.side > 0)
            if opposite and self._policy.exit_on_opposite and not busy:
                self._queue_exit(held, "opposite_signal", p, record)
            else:
                record["status"] = "ignored:position_open"
        elif busy:
            record["status"] = "ignored:order_pending"
        elif p.intent == Intent.FLAT:
            record["status"] = "ignored:no_position"
        else:
            side = 1 if p.intent == Intent.LONG else -1
            self._pending = _Order(
                "entry", side, p.rationale, p, p.generated_at + self._latency, p.valid_until
            )
            record["status"] = "queued_entry"

    def _queue_exit(self, held: _Open, reason: str, p: Proposal, record: dict[str, Any]) -> None:
        self._pending = _Order(
            "exit", -held.side, reason, p, p.generated_at + self._latency, _NEVER
        )
        record["status"] = "queued_exit"

    def _enter(self, order: _Order, ts: int, mid: Decimal) -> None:
        proposal = order.proposal
        session = self._calendar.containing(ts)
        if proposal is None or session is None:
            raise DataError("entry needs a proposal and a classified session")
        quantity = self._sizing.quantity(mid, self._multiplier, self._lot)
        account = self.cache.account_for_venue(self._venue)
        balance = account.balance_total(USD).as_decimal()
        loss = max(-self._pnl.get(session.day, Decimal(0)), Decimal(0))
        reasons = list(
            self._limits.check_entry(
                quantity=quantity,
                price=mid,
                multiplier=self._multiplier,
                balance=balance,
                data_age_ns=ts - proposal.data_asof,
                entries_today=self._entries.get(session.day, 0),
                loss_today=loss,
            )
        )
        lead = self._policy.flatten_lead_seconds
        if lead is not None and ts >= session.close - lead * SECOND:
            reasons.append("entry_after_flatten_time")
        if reasons:
            self.rejections.append(
                {
                    "ts": ts,
                    "source": "risk",
                    "proposal_id": proposal.proposal_id,
                    "reasons": sorted(reasons),
                }
            )
            self._status(proposal, "rejected:" + ",".join(sorted(reasons)))
            return
        self._entries[session.day] = self._entries.get(session.day, 0) + 1
        self._submit(
            "entry", order.side, quantity, order.reason, proposal.proposal_id, reduce_only=False
        )

    def _exit(self, reason: str) -> None:
        held = self._open
        if held is None:
            return
        self._pending = None
        self._submit("exit", -held.side, held.quantity, reason, held.proposal_id, reduce_only=True)

    def _submit(
        self,
        kind: str,
        side: int,
        quantity: Decimal,
        reason: str,
        proposal_id: str,
        *,
        reduce_only: bool,
    ) -> None:
        instrument = self.cache.instrument(self._iid)
        order = self.order_factory.market(
            self._iid,
            OrderSide.BUY if side > 0 else OrderSide.SELL,
            instrument.make_qty(quantity),
            time_in_force=TimeInForce.IOC,
            reduce_only=reduce_only,
        )
        self._inflight = _Inflight(kind, side, quantity, reason, proposal_id)
        self.submit_order(order)

    def _engine_reject(self, event: Any) -> None:
        flight = self._inflight
        self.rejections.append(
            {
                "ts": event.ts_event,
                "source": "engine",
                "proposal_id": flight.proposal_id if flight else "",
                "reasons": [str(getattr(event, "reason", "rejected"))],
            }
        )
        self._inflight = None
        if flight is not None and flight.kind == "entry":
            self._status_id(flight.proposal_id, "rejected:engine")

    def _status(self, proposal: Proposal | None, status: str) -> None:
        if proposal is not None:
            self._status_id(proposal.proposal_id, status)

    def _status_id(self, proposal_id: str, status: str) -> None:
        if proposal_id in self._records:
            self._records[proposal_id]["status"] = status

    def finalize(self) -> dict[str, Any] | None:
        """Mark intents that never executed and describe any position left open."""
        if self._pending is not None and self._pending.kind == "entry":
            self._status(self._pending.proposal, "unfilled_at_end")
        held = self._open
        if held is None:
            return None
        return {
            "side": "LONG" if held.side > 0 else "SHORT",
            "quantity": str(held.quantity),
            "entry_ts": held.entry_ts,
            "entry_price": str(held.entry_price),
            "entry_commission": str(held.entry_commission),
        }


def _quote(tick_instrument: InstrumentId, c: Candle, spec: InstrumentSpec, offset: Decimal) -> Any:
    fmt = f".{spec.precision}f"
    bid = max(c.open - offset, spec.tick)
    return QuoteTick(
        tick_instrument,
        Price.from_str(format(bid, fmt)),
        Price.from_str(format(c.open + offset, fmt)),
        Quantity.from_int(10_000_000),
        Quantity.from_int(10_000_000),
        c.start,
        c.start,
    )


def software() -> dict[str, Any]:
    root = Path(__file__).parents[1]
    sources = sorted(
        p for folder in ("strategies", "backtest", "data") for p in (root / folder).rglob("*.py")
    )
    code = b"".join(str(p.relative_to(root)).encode() + p.read_bytes() for p in sources)
    return {
        "code_sha256": digest(code),
        "nautilus": version("nautilus-trader"),
        "python": platform.python_version(),
        "tzdata": TZ_VERSION,
        "quantlab": __version__,
    }


def run_on(config: BacktestConfig, data: MarketData) -> BacktestResult:
    """Run `config` over `data` (synthetic generation or injected scripted candles)."""
    spec = config.instrument
    if data.instrument != spec:
        raise DataError("market data and configuration disagree on the instrument")
    instrument = make_instrument(spec)
    iid = InstrumentId.from_str(spec.id)
    bar_type = BarType.from_str(f"{spec.id}-1-MINUTE-LAST-EXTERNAL")
    offset = (config.costs.half_spread_ticks + config.costs.slippage_ticks) * spec.tick
    bars = [
        Bar(
            bar_type,
            Price.from_str(str(c.open)),
            Price.from_str(str(c.high)),
            Price.from_str(str(c.low)),
            Price.from_str(str(c.close)),
            Quantity.from_int(c.volume),
            c.end,
            c.available,
        )
        for c in data.candles
    ]
    quotes = [_quote(iid, c, spec, offset) for c in data.candles]
    strategy = RuleStrategy(
        make_agent(config, data.calendar),
        config.strategy.exit,
        config.sizing,
        config.risk,
        spec,
        data.calendar,
        config.costs.order_latency_seconds * SECOND,
    )
    engine = BacktestEngine(
        BacktestEngineConfig(logging=LoggingConfig(bypass_logging=True), run_analysis=False)
    )
    try:
        venue = Venue(spec.venue)
        engine.add_venue(
            venue=venue,
            oms_type=OmsType.NETTING,
            account_type=AccountType.MARGIN,
            starting_balances=[Money(config.capital, USD)],
            base_currency=USD,
            fill_model=FillModel(prob_fill_on_limit=1.0, prob_slippage=0.0, random_seed=0),
            fee_model=ConfiguredFees(config.costs),
            bar_execution=False,
        )
        engine.add_instrument(instrument)
        engine.add_strategy(strategy)
        engine.add_data(bars)
        engine.add_data(quotes)
        engine.run()
        run = engine.get_result()
        balance = engine.cache.account_for_venue(venue).balance_total(USD).as_decimal()
        orders, positions, iterations = run.total_orders, run.total_positions, run.iterations
    finally:
        engine.dispose()
    open_at_end = strategy.finalize()
    trades = tuple(strategy.trades)
    pending_fee = Decimal(open_at_end["entry_commission"]) if open_at_end else Decimal(0)
    ledger = config.capital + sum((t.net_pnl for t in trades), Decimal(0)) - pending_fee
    fills = 2 * len(trades) + (1 if open_at_end else 0)
    tolerance = Decimal("0.01") * fills
    window = sum(s.close - s.open for s in data.calendar.sessions)
    payload = config.payload()
    return BacktestResult(
        payload,
        digest(canonical(payload)),
        data.sha256,
        {
            "instrument": spec.id,
            "sessions": len(data.calendar.sessions),
            "candles": len(data.candles),
            "first_ts": data.candles[0].start,
            "last_ts": data.candles[-1].end,
        },
        software(),
        {"orders": orders, "positions": positions, "iterations": iterations},
        trades,
        tuple(strategy.proposals),
        tuple(strategy.rejections),
        metrics(list(trades), config.capital, window),
        {
            "engine_balance": str(balance),
            "ledger_balance": str(ledger),
            "difference": str(balance - ledger),
            "tolerance": str(tolerance),
            "ok": abs(balance - ledger) <= tolerance,
        },
        open_at_end,
    )


def run_backtest(config: BacktestConfig) -> BacktestResult:
    return run_on(config, generate(config.data, config.instrument))
