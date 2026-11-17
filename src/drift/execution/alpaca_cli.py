"""Bounded, supervised NVDA/ITSM paper observation; separate from SIP research acceptance."""

import argparse
import json
import os
import time
from dataclasses import asdict, replace
from decimal import Decimal
from pathlib import Path
from typing import Any

from drift.backtest.risk import RiskLimits, Sizing
from drift.data.alpaca import Credentials
from drift.data.equity import PilotRequest
from drift.data.model import NY, SECOND, DataError, instant, local_ns
from drift.execution.alpaca import (
    AlpacaHTTP,
    AlpacaPaperConfig,
    AlpacaTransport,
    calendar_window,
    ns,
    number,
)
from drift.execution.paper import PENDING, PaperGate, Snapshot
from drift.strategies.calendar import Calendar
from drift.strategies.proposal import Intent, new_proposal
from drift.strategies.rule.statistical.itsm import ItsmParams, ItsmRule


def private_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def configuration(path: Path, account_id: str, *, orders: bool) -> AlpacaPaperConfig:
    """Persist the initial paper account binding and small explicit simulation limits."""
    if not path.exists():
        private_json(
            path,
            {
                "account_id": account_id,
                "capital_limit": "1000",
                "shares": "1",
                "max_quantity": "1",
                "max_notional": "1000",
                "max_leverage": "1",
                "max_session_loss": "10",
                "max_entries_per_session": 1,
                "max_data_age_seconds": 30,
                "state_max_age_seconds": 30,
                "min_order_interval_seconds": 10,
            },
        )
    if path.stat().st_size > 8192:
        raise DataError("paper configuration exceeds size limit")
    raw = json.loads(path.read_bytes())
    if raw["account_id"] != account_id:
        raise DataError("paper credentials do not match the locally bound account")
    return AlpacaPaperConfig(
        raw["account_id"],
        PilotRequest().instrument,
        RiskLimits(
            number(raw["max_quantity"]),
            number(raw["max_notional"]),
            number(raw["max_leverage"]),
            raw["max_entries_per_session"],
            number(raw["max_session_loss"]),
            raw["max_data_age_seconds"],
        ),
        Sizing("fixed_quantity", number(raw["shares"])),
        number(raw["capital_limit"]),
        raw["min_order_interval_seconds"],
        raw["state_max_age_seconds"],
        connection_authorized=True,
        orders_authorized=orders,
    )


class PaperSession:
    """One ITSM decision per session; position exits begin two minutes before close.

    Long only, no parameter search. Entries use completed, observed IEX minutes, then a
    fresh quote through central risk. Three bounded IOC exit attempts; failure halts for
    supervision. No queued weekend orders, extended hours or unattended promotion.
    """

    def __init__(
        self,
        http: AlpacaHTTP,
        transport: AlpacaTransport,
        gate: PaperGate,
        calendar: Calendar,
        events: Path,
    ) -> None:
        self.http, self.transport, self.gate = http, transport, gate
        self.calendar, self.events = calendar, events

    def event(self, kind: str, **values: Any) -> None:
        fd = os.open(self.events, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a") as stream:
            stream.write(json.dumps({"at_ns": time.time_ns(), "kind": kind, **values}) + "\n")

    def flatten(self, now: int) -> None:
        day = instant(now).astimezone(NY).date().isoformat()
        attempts = self.gate.db.execute(
            "SELECT COUNT(*) FROM orders WHERE day=? AND json_extract(payload,'$.side')=-1",
            (day,),
        ).fetchone()[0]
        if attempts >= 3:
            self.gate.halt("exit_attempt_limit")
            raise DataError("three IOC exits failed; supervised paper-position resolution required")
        quote = self.http.quote()
        now = time.time_ns()
        proposal = new_proposal(
            agent_id="paper-exit",
            strategy_id="PAPER-ITSM-IEX-001",
            instrument_id=self.gate.config.instrument.id,
            version="paper-ops-v1",
            generated_at=now,
            valid_seconds=10,
            horizon_seconds=0,
            intent=Intent.FLAT,
            rationale="supervised paper time exit",
            reasons=(),
            refs=("alpaca:iex:NVDA",),
        )
        order = self.gate.submit(proposal, quote, now)
        self.event("exit_submitted", client_order_id=order.order_id)

    def tick(self, now: int, snapshot: Snapshot) -> bool:
        """Return true only when the session time-exit is flat and all orders terminal."""
        session = self.calendar.containing(now)
        if session is None or now >= session.close:
            if snapshot.position or any(s in PENDING for s in self.gate.orders().values()):
                raise DataError("market closed with unresolved paper exposure; inspect account")
            return True
        pending = any(s in PENDING for s in self.gate.orders().values())
        if now >= session.close - 120 * SECOND:
            if not pending and snapshot.position:
                self.flatten(now)
            return not pending and not snapshot.position
        decision = local_ns(session.day, "15:30")
        key = "paper_decision:" + session.day
        if now <= decision + SECOND or self.gate._meta(key):
            return False
        self.gate._set(key, "consumed")  # Crash/restart must never create another entry.
        if now > decision + 30 * SECOND or not session.full:
            self.event("abstain", reasons=["missed_decision_or_early_close"])
            return False
        candles = self.http.candles(self.calendar, now)
        previous = self.calendar.previous(session.day)
        prior_close = next((c.close for c in candles if previous and c.end == previous.close), None)
        current = [c for c in candles if c.day == session.day]
        if prior_close and current and abs(current[0].open / prior_close - 1) > Decimal("0.3"):
            # A diagnostic guard, not a corporate-action certification or adjusted series.
            self.event("abstain", reasons=["unreviewed_action_or_extreme_overnight_move"])
            return False
        rule = ItsmRule(
            ItsmParams(allow_short=False),
            self.gate.config.instrument.id,
            self.calendar,
            strategy_id="PAPER-ITSM-IEX-001",
        )
        proposal = None
        for candle in candles:
            result = rule.on_candle(candle)
            if result is not None and candle.day == session.day:
                proposal = result
        if proposal is None:
            self.event("abstain", reasons=["decision_candle_missing"])
            return False
        proposal = replace(proposal, input_refs=proposal.input_refs + ("alpaca:iex:NVDA:raw",))
        self.event("proposal", proposal={**asdict(proposal), "intent": str(proposal.intent)})
        if proposal.intent == Intent.LONG:
            quote = self.http.quote()
            now = time.time_ns()
            if now > decision + 30 * SECOND:
                self.event("abstain", reasons=["decision_fetch_too_late"])
                return False
            order = self.gate.submit(proposal, quote, now)
            self.event("entry_submitted", client_order_id=order.order_id)
        return False


def run(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if not args.authorize_paper_connection or args.credentials_file is None:
        parser.error("paper commands need --authorize-paper-connection and --credentials-file")
    if args.command != "paper-status" and not args.authorize_paper_orders:
        parser.error("paper-run/kill require --authorize-paper-orders")
    if not 1 <= args.max_seconds <= 25200:
        parser.error("--max-seconds must be 1..25200")
    root = args.output or Path("data/alpaca-paper")
    gate = None
    try:
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        http = AlpacaHTTP(
            Credentials.read(args.credentials_file),
            authorized=True,
            receipts=root / "receipts.jsonl",
        )
        account, clock = http.account(), http.clock()
        cfg = configuration(root / "config.json", account["id"], orders=args.authorize_paper_orders)
        now = time.time_ns()
        if not 0 <= now - ns(clock["timestamp"]) <= 10 * SECOND:
            raise DataError("stale paper broker clock")
        if args.command == "paper-status":
            positions = http._request("GET", "/positions")
            orders = http._request("GET", "/orders", {"status": "open", "limit": "500"})
            quote = http.quote()
            report = {
                "environment": "paper",
                "account_status": account["status"],
                "market_open": clock["is_open"],
                "next_open": clock["next_open"],
                "positions": len(positions),
                "open_orders": len(orders),
                "feed": "iex",
                "quote_usable_now": 0 < quote.bid <= quote.ask
                and 0
                <= time.time_ns() - quote.available_at
                <= cfg.risk.max_data_age_seconds * SECOND,
                "orders_sent": 0,
            }
            private_json(root / "status.json", report)
            print(json.dumps(report, sort_keys=True))
            return
        day = instant(now).astimezone(NY).date().isoformat()
        if args.command == "paper-run" and not clock["is_open"]:
            raise DataError(
                "paper market is closed; no order queued. Use paper-status for next open"
            )
        calendar = http.calendar(*calendar_window(day))
        transport = AlpacaTransport(cfg, http)
        gate = PaperGate(cfg, transport, root / "paper.sqlite", calendar)
        transport.attach(gate)
        if args.command == "paper-kill":
            gate.kill()
            print("Paper halt persisted; cancellation requested for known pending orders.")
            return
        asset = http._request("GET", "/assets/NVDA")
        if asset.get("tradable") is not True or asset.get("status") != "active":
            raise DataError("NVDA is not active/tradable in the paper account")
        session = PaperSession(http, transport, gate, calendar, root / "events.jsonl")
        deadline = time.monotonic() + args.max_seconds
        first = True
        while time.monotonic() < deadline:
            snapshot = transport.refresh(resume=args.resume_paper if first else False)
            first = False
            if session.tick(time.time_ns(), snapshot):
                print("Paper session finished flat; all known orders terminal.")
                return
            now = time.time_ns()
            near_decision = now >= local_ns(day, "15:30") - 60 * SECOND
            time.sleep(5 if near_decision or snapshot.position else 20)
        snapshot = transport.refresh()
        if snapshot.position:
            session.flatten(time.time_ns())
            time.sleep(2)
            snapshot = transport.refresh()
        if snapshot.position or any(s in PENDING for s in gate.orders().values()):
            raise DataError(
                "paper duration ended with unresolved exposure; inspect account/journal"
            )
        print("Paper duration ended flat; all known orders terminal.")
    except KeyboardInterrupt:
        if gate is not None:
            gate.kill()
        parser.exit(2, "Paper runner interrupted; inspect positions. Halt does not liquidate.\n")
    except DataError as exc:
        if gate is not None:
            gate.halt("paper_runner_stopped")
        parser.exit(2, f"Paper operation stopped: {exc}\n")
    except (OSError, KeyError, TypeError, ValueError):
        if gate is not None:
            gate.halt("paper_runner_stopped")
        parser.exit(2, "Paper operation stopped safely; inspect private journal/account.\n")
    finally:
        if gate is not None:
            gate.close()
