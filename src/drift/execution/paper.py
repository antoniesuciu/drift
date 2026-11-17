"""Shared paper execution gate and durable intent/fill journal for broker adapters."""

import fcntl
import json
import sqlite3
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from pathlib import Path
from typing import Protocol

from drift.data.model import SECOND, DataError, canonical, digest
from drift.execution.model import PaperOrder, PaperPolicy
from drift.strategies.calendar import Calendar
from drift.strategies.proposal import Intent, Proposal


class PaperTransport(Protocol):
    def managed_accounts(self) -> tuple[str, ...]: ...
    def submit(self, order: PaperOrder) -> None: ...
    def cancel(self, order_id: str) -> None: ...


@dataclass(frozen=True, slots=True)
class Quote:
    bid: Decimal
    ask: Decimal
    available_at: int
    realtime: bool


@dataclass(frozen=True, slots=True)
class Snapshot:
    cash: Decimal
    position: int
    available_at: int
    loss_today: Decimal


PENDING = ("PREPARED", "SUBMITTED", "SENDING", "ACK", "PARTIAL", "CANCEL_REQUESTED", "UNKNOWN")
TERMINAL = ("FILLED", "CANCELLED", "REJECTED")


class PaperGate:
    """Single writer, long-only, one outstanding intent; all starts require reconciliation.

    SQLite commits PREPARED before a transport call. Any uncertain outcome halts; no resend.
    The initial connection requires a flat isolated account and establishes the cash baseline.
    Other activity/cash transfers require operator review, never silent ledger adoption.
    """

    def __init__(
        self, config: PaperPolicy, transport: PaperTransport, journal: Path, calendar: Calendar
    ) -> None:
        self.config, self.transport, self.calendar = config, transport, calendar
        journal.parent.mkdir(parents=True, exist_ok=True)
        self._lock = journal.with_suffix(journal.suffix + ".lock").open("a")
        try:
            fcntl.flock(self._lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self._lock.close()
            raise DataError("paper journal already has an active writer") from None
        self.db = sqlite3.connect(journal)
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS orders (
              id TEXT PRIMARY KEY, proposal TEXT UNIQUE, payload TEXT, status TEXT, day TEXT);
            CREATE TABLE IF NOT EXISTS fills (
              id TEXT PRIMARY KEY, order_id TEXT, quantity INTEGER, price TEXT, fee TEXT);
        """)
        binding = digest(
            canonical(
                {
                    "account": digest(config.account_id.encode()),
                    "instrument": config.instrument.id,
                    "mode": "paper",
                    "broker": config.broker,
                }
            )
        )
        existing = self._meta("binding")
        if existing is not None and existing != binding:
            self.close()
            raise DataError("journal belongs to a different paper account/instrument")
        self._set("binding", binding)
        self._ready = False
        self._snapshot: Snapshot | None = None

    def _meta(self, key: str) -> str | None:
        row = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return str(row[0]) if row else None

    def _set(self, key: str, value: str) -> None:
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (key, value))

    def close(self) -> None:
        self.db.close()
        self._lock.close()

    def halt(self, reason: str = "operator_halt") -> None:
        self._ready = False
        self._set("halt", reason)

    def _accounts(self) -> None:
        if not self.config.connection_authorized:
            raise DataError("paper connection is not authorized")
        try:
            if self.transport.managed_accounts() != (self.config.account_id,):
                raise DataError("managed account does not match the isolated paper allow-list")
        except Exception:
            self.halt("account_or_connection_failure")
            raise DataError("paper account/connection verification failed") from None

    def orders(self) -> dict[str, str]:
        return dict(self.db.execute("SELECT id,status FROM orders"))

    def _ledger(self) -> tuple[Decimal, int]:
        cash, position = Decimal(self._meta("initial_cash") or "0"), 0
        for payload, quantity, price, fee in self.db.execute(
            "SELECT o.payload,f.quantity,f.price,f.fee FROM fills f "
            "JOIN orders o ON o.id=f.order_id"
        ):
            side = json.loads(payload)["side"]
            position += side * quantity
            if fee is None:
                raise DataError("execution commission is unconfirmed; reconciliation blocked")
            cash -= side * quantity * Decimal(price) + Decimal(fee)
        return cash, position

    def reconcile(
        self, snapshot: Snapshot, reports: Mapping[str, str], now: int, *, resume: bool = False
    ) -> None:
        """Reports cover every known order, including terminal ones and unknown submissions.

        Fill events must be imported first. Absence from open orders is not cancellation proof.
        """
        self._ready = False
        self._accounts()
        if (
            not snapshot.cash.is_finite()
            or not snapshot.loss_today.is_finite()
            or snapshot.loss_today < 0
            or type(snapshot.position) is not int
            or not 0 <= now - snapshot.available_at <= self.config.state_max_age_seconds * SECOND
        ):
            self.halt("invalid_or_stale_snapshot")
            raise DataError("invalid/stale broker snapshot")
        local = self.orders()
        if any(int(self._meta("broker_filled:" + oid) or "0") > self._filled(oid) for oid in local):
            raise DataError("broker reports fills awaiting complete execution receipts")
        if set(reports) != set(local) or any(
            s not in (*TERMINAL, "ACK", "PARTIAL") for s in reports.values()
        ):
            self.halt("unresolved_broker_orders")
            raise DataError("incomplete/unknown broker order state")
        if self._meta("initial_cash") is None:
            if snapshot.position or local:
                self.halt("initial_state_not_flat")
                raise DataError("first reconciliation requires an isolated flat paper account")
            self._set("initial_cash", str(snapshot.cash))
        cash, position = self._ledger()
        if position != snapshot.position or abs(cash - snapshot.cash) > Decimal("0.01"):
            self.halt("ledger_mismatch")
            raise DataError("broker/local positions or cash do not reconcile")
        for order_id, status in reports.items():
            quantity = self._filled(order_id)
            requested = self._order(order_id).quantity
            if (
                (status == "FILLED" and quantity != requested)
                or (status in ("ACK", "REJECTED") and quantity != 0)
                or (status == "PARTIAL" and not 0 < quantity < requested)
            ):
                self.halt("fill_status_mismatch")
                raise DataError("broker order status and recorded fills disagree")
            with self.db:
                self.db.execute("UPDATE orders SET status=? WHERE id=?", (status, order_id))
        self._snapshot = snapshot
        if self._meta("halt") and not resume:
            raise DataError("explicit operator resume required after reconciliation")
        self._set("halt", "")
        self._ready = True

    def _order(self, order_id: str) -> PaperOrder:
        row = self.db.execute("SELECT payload FROM orders WHERE id=?", (order_id,)).fetchone()
        if row is None:
            self.halt("unknown_order_event")
            raise DataError("unknown paper order")
        raw = json.loads(row[0])
        raw["limit"] = Decimal(raw["limit"])
        return PaperOrder(**raw)

    def _filled(self, order_id: str) -> int:
        return int(
            self.db.execute(
                "SELECT COALESCE(SUM(quantity),0) FROM fills WHERE order_id=?", (order_id,)
            ).fetchone()[0]
        )

    def acknowledge(self, order_id: str) -> None:
        """Acknowledgement keeps the reservation; it is never a fill or terminal proof."""
        self._order(order_id)
        with self.db:
            self.db.execute(
                "UPDATE orders SET status='ACK' WHERE id=? "
                "AND status IN ('PREPARED','SUBMITTED','SENDING','UNKNOWN')",
                (order_id,),
            )

    def broker_filled(self, order_id: str, cumulative: int) -> None:
        """A status callback's fill count cannot replace actual execution/commission receipts."""
        order = self._order(order_id)
        if type(cumulative) is not int or not 0 <= cumulative <= order.quantity:
            self.halt("invalid_broker_fill_count")
            raise DataError("broker cumulative fill count is invalid")
        recorded = self._meta("broker_filled:" + order_id)
        prior = int(recorded or "0")
        if recorded is None or cumulative > prior:
            self._set("broker_filled:" + order_id, str(max(prior, cumulative)))
        if cumulative > self._filled(order_id):
            self._ready = False

    def confirmed_fill(self, execution_id: str, order_id: str, quantity: int) -> bool:
        row = self.db.execute(
            "SELECT order_id,quantity,fee FROM fills WHERE id=?",
            (execution_id,),
        ).fetchone()
        return bool(row and row[0] == order_id and row[1] == quantity and row[2] is not None)

    def native_preflight(self, order: PaperOrder, now: int, *, sending: bool = False) -> None:
        """Recheck the durable reservation at the native queue and actual wire boundary.

        SENDING is persisted before the broker call; an exception/crash cannot authorize resend.
        """
        if (
            not self.config.orders_authorized
            or not self._ready
            or self._meta("halt")
            or self._order(order.order_id) != order
            or not order.created_at <= now < order.valid_until
        ):
            raise DataError("native paper approval is absent, halted, changed or expired")
        self._accounts()
        status = self.orders()[order.order_id]
        if status not in ("PREPARED", "SUBMITTED"):
            raise DataError("native reservation already sent or no longer pending submission")
        if sending:
            with self.db:
                self.db.execute("UPDATE orders SET status='SENDING' WHERE id=?", (order.order_id,))

    def submit(self, proposal: Proposal, quote: Quote, now: int) -> PaperOrder:
        cfg, snapshot = self.config, self._snapshot
        if not cfg.orders_authorized:
            raise DataError("paper orders are not authorized")
        if not self._ready or self._meta("halt") or snapshot is None:
            raise DataError("paper execution halted; reconciliation required")
        self._accounts()
        session = self.calendar.containing(now)
        if (
            session is None
            or not session.open <= now < session.close
            or not proposal.live_at(now)
            or proposal.instrument_id != cfg.instrument.id
            or proposal.family != "RULE"
            or proposal.intent not in (Intent.LONG, Intent.FLAT)
        ):
            raise DataError("unsupported/expired proposal, instrument or cash session")
        if (
            quote.realtime is not True
            or not quote.bid.is_finite()
            or not quote.ask.is_finite()
            or not 0 < quote.bid <= quote.ask
            or not 0 <= now - quote.available_at <= cfg.risk.max_data_age_seconds * SECOND
            or not 0 <= now - proposal.data_asof <= cfg.risk.max_data_age_seconds * SECOND
            or not 0 <= now - snapshot.available_at <= cfg.state_max_age_seconds * SECOND
        ):
            raise DataError("stale/future/delayed data or unavailable portfolio state")
        if self.db.execute(
            "SELECT 1 FROM orders WHERE proposal=?", (proposal.proposal_id,)
        ).fetchone():
            raise DataError("duplicate proposal; no resend")
        if any(status in PENDING for status in self.orders().values()):
            raise DataError("pending/uncertain order reserves exposure; no second order")
        cash, position = self._ledger()
        side = 1 if proposal.intent == Intent.LONG else -1
        quantity = int(cfg.sizing.amount) if side == 1 else position
        tick = cfg.instrument.tick
        raw_price = quote.ask if side == 1 else quote.bid
        price = (raw_price / tick).to_integral_value(
            rounding=ROUND_CEILING if side == 1 else ROUND_FLOOR
        ) * tick
        if quantity <= 0 or position < 0:
            raise DataError("no whole-share quantity/long position to trade")
        previous = int(self._meta("last_submit") or "0")
        if now - previous < cfg.min_order_interval_seconds * SECOND:
            raise DataError("paper order rate limit")
        entries = self.db.execute(
            "SELECT COUNT(*) FROM orders WHERE day=? AND json_extract(payload,'$.side')=1",
            (session.day,),
        ).fetchone()[0]
        if side == 1:
            reasons = cfg.risk.check_entry(
                quantity=Decimal(position + quantity),
                price=price,
                multiplier=Decimal(1),
                balance=min(cash + position * quote.bid, cfg.capital_limit),
                data_age_ns=now - quote.available_at,
                entries_today=entries,
                loss_today=snapshot.loss_today,
            )
            if reasons or quantity * price > cash:
                raise DataError(
                    "paper risk rejected: " + ",".join(reasons or ("insufficient_cash",))
                )
        order = PaperOrder(
            "QTL-" + digest(proposal.proposal_id.encode())[:28],
            proposal.proposal_id,
            cfg.instrument.id,
            side,
            quantity,
            price,
            now,
            min(
                proposal.valid_until,
                session.close,
                quote.available_at + cfg.risk.max_data_age_seconds * SECOND,
                proposal.data_asof + cfg.risk.max_data_age_seconds * SECOND,
                snapshot.available_at + cfg.state_max_age_seconds * SECOND,
            ),
        )
        payload = asdict(order) | {"limit": str(order.limit)}
        with self.db:
            self.db.execute(
                "INSERT INTO orders VALUES (?,?,?,?,?)",
                (
                    order.order_id,
                    proposal.proposal_id,
                    json.dumps(payload),
                    "PREPARED",
                    session.day,
                ),
            )
        self._set("last_submit", str(now))
        try:
            self.transport.submit(order)
        except Exception:
            with self.db:
                self.db.execute(
                    "UPDATE orders SET status='UNKNOWN' WHERE id=? "
                    "AND status IN ('PREPARED','SUBMITTED','SENDING')",
                    (order.order_id,),
                )
            self.halt("unknown_submission")
            raise DataError(
                "submission outcome unknown; reconcile before any further order"
            ) from None
        with self.db:
            self.db.execute(
                "UPDATE orders SET status='SUBMITTED' WHERE id=? AND status='PREPARED'",
                (order.order_id,),
            )
        return order

    def record_fill(
        self, execution_id: str, order_id: str, quantity: int, price: Decimal, fee: Decimal | None
    ) -> None:
        order = self._order(order_id)
        if (
            type(quantity) is not int
            or quantity <= 0
            or not price.is_finite()
            or price <= 0
            or (fee is not None and (not fee.is_finite() or fee < 0))
            or not execution_id
            or (order.side == 1 and price > order.limit)
            or (order.side == -1 and price < order.limit)
        ):
            self.halt("invalid_fill")
            raise DataError("invalid paper fill")
        row = (execution_id, order_id, quantity, str(price), str(fee) if fee is not None else None)
        existing = self.db.execute("SELECT * FROM fills WHERE id=?", (execution_id,)).fetchone()
        if existing:
            if existing[:3] != row[:3] or Decimal(existing[3]) != price:
                self.halt("conflicting_execution")
                raise DataError("conflicting duplicate execution")
            if fee is None:
                return  # A repeated pending report cannot downgrade a confirmed commission.
            if existing[4] is None:
                with self.db:
                    self.db.execute("UPDATE fills SET fee=? WHERE id=?", (str(fee), execution_id))
                self._ready = False
            elif Decimal(existing[4]) != fee:
                self.halt("conflicting_execution")
                raise DataError("conflicting duplicate execution commission")
            return
        if self._filled(order_id) + quantity > order.quantity:
            self.halt("overfill")
            raise DataError("fill exceeds reserved quantity")
        status = "FILLED" if self._filled(order_id) + quantity == order.quantity else "PARTIAL"
        if self.orders()[order_id] == "CANCELLED" and status != "FILLED":
            status = "CANCELLED"  # A late partial fill does not undo a confirmed cancellation.
        with self.db:
            self.db.execute("INSERT INTO fills VALUES (?,?,?,?,?)", row)
            self.db.execute("UPDATE orders SET status=? WHERE id=?", (status, order_id))
        self._ready = False  # Fresh broker reconciliation is mandatory before another intent.
        if fee is None:
            self.halt("commission_unconfirmed")

    def terminal(self, order_id: str, status: str) -> None:
        order = self._order(order_id)
        if status not in ("REJECTED", "CANCELLED") or (
            status == "REJECTED" and self._filled(order_id)
        ):
            self.halt("invalid_terminal_event")
            raise DataError("invalid terminal paper event")
        if self._filled(order_id) == order.quantity:
            return  # Fill won the cancel race.
        with self.db:
            self.db.execute("UPDATE orders SET status=? WHERE id=?", (status, order_id))
        self._ready = False

    def kill(self) -> None:
        self.halt("operator_kill")
        pending = [
            (order_id, status) for order_id, status in self.orders().items() if status in PENDING
        ]
        if not pending:
            return
        if not self.config.orders_authorized:
            raise DataError(
                "halt persisted; cancellation requires explicit paper-order authorization"
            )
        self._accounts()
        for order_id, status in pending:
            if status in PENDING:
                with self.db:
                    self.db.execute(
                        "UPDATE orders SET status='CANCEL_REQUESTED' WHERE id=?", (order_id,)
                    )
                try:
                    self.transport.cancel(order_id)
                except Exception:
                    self.halt("cancel_outcome_unknown")
                    raise DataError(
                        "cancel outcome unknown; broker reconciliation required"
                    ) from None
