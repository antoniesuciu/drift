"""Offline safety/lifecycle tests; only FakeTransport can receive orders here."""

import sqlite3
from dataclasses import replace
from decimal import Decimal

import pytest

from drift.backtest.risk import RiskLimits, Sizing
from drift.data.equity import PilotRequest
from drift.data.model import SECOND, DataError, local_ns
from drift.execution.ibkr import PaperConfig, node_config
from drift.execution.paper import PaperGate, Quote, Snapshot
from drift.strategies.calendar import Calendar, SessionSpec
from drift.strategies.proposal import Intent, new_proposal

DAY = "2021-07-20"
NOW = local_ns(DAY, "15:30") + SECOND


class FakeTransport:
    accounts = ("DU1234567",)
    error = False
    cancel_error = False

    def __init__(self):
        self.sent, self.cancelled = [], []
        self.before_submit = lambda order: None

    def managed_accounts(self):
        return self.accounts

    def submit(self, order):
        self.before_submit(order)
        self.sent.append(order)
        if self.error:
            raise TimeoutError("sensitive broker diagnostic")

    def cancel(self, order_id):
        self.cancelled.append(order_id)
        if self.cancel_error:
            raise TimeoutError("unknown cancellation")


def config(**changes):
    cfg = PaperConfig(
        "DU1234567",
        PilotRequest().instrument,
        RiskLimits(Decimal(10), Decimal(2000), Decimal(1), 3, Decimal(100), 2),
        Sizing("fixed_quantity", Decimal(2)),
        Decimal(10000),
        2,
        5,
        connection_authorized=True,
        orders_authorized=True,
    )
    return replace(cfg, **changes)


def proposal(now=NOW, intent=Intent.LONG, **changes):
    p = new_proposal(
        agent_id="itsm-001",
        strategy_id="ITSM-001",
        instrument_id="NVDA.XNAS",
        version="test-1",
        generated_at=now,
        valid_seconds=60,
        horizon_seconds=60,
        intent=intent,
        rationale="synthetic",
        reasons=(),
        refs=("synthetic:quote",),
    )
    return replace(p, **changes)


def quote(now=NOW, **changes):
    return replace(Quote(Decimal("100.00"), Decimal("100.01"), now, True), **changes)


def snapshot(now=NOW, **changes):
    return replace(Snapshot(Decimal(10000), 0, now, Decimal(0)), **changes)


def gate_at(tmp_path, cfg=None):
    transport = FakeTransport()
    gate = PaperGate(
        cfg or config(), transport, tmp_path / "paper.sqlite", Calendar((SessionSpec(DAY),))
    )
    return gate, transport


@pytest.mark.parametrize(
    "patch",
    [
        {"account_id": "U1234567"},
        {"port": 7496},
        {"port": 4001},
        {"host": "remote"},
        {"min_order_interval_seconds": 0},
        {"state_max_age_seconds": 0},
        {"orders_authorized": True, "connection_authorized": False},
        {"sizing": Sizing("fixed_quantity", Decimal("1.5"))},
    ],
)
def test_paper_configuration_rejects_live_or_unbounded_options(patch):
    with pytest.raises(DataError):
        config(**patch)


def test_real_installed_ib_config_and_native_order_translation_without_connecting(tmp_path):
    cfg = config(connection_authorized=False, orders_authorized=False)
    prepared = node_config(cfg)
    client = prepared.exec_clients["IBPAPER"]
    assert client.account_id == "DU1234567" and client.ibg_port == 7497
    assert client.dockerized_gateway is None and not client.routing.default
    assert prepared.risk_engine.bypass is False
    assert client.instrument_provider.symbol_to_mic_venue == {"NVDA": "XNAS"}
    assert "DU1234567" not in repr(cfg)
    gate, transport = gate_at(tmp_path)
    gate.reconcile(snapshot(), {}, NOW)
    order = gate.submit(proposal(), quote(), NOW)
    native = order.native()
    assert str(native.instrument_id) == "NVDA.XNAS"
    assert str(native.client_order_id) == order.order_id
    assert native.quantity.as_decimal() == 2 and native.price.as_decimal() == Decimal("100.01")
    assert native.time_in_force.name == "IOC" and native.side.name == "BUY"
    assert transport.sent == [order]
    gate.close()


def test_missing_authorization_and_startup_reconciliation_deny_orders(tmp_path):
    gate, transport = gate_at(
        tmp_path, config(connection_authorized=False, orders_authorized=False)
    )
    with pytest.raises(DataError, match="not authorized"):
        gate.reconcile(snapshot(), {}, NOW)
    with pytest.raises(DataError, match="not authorized"):
        gate.submit(proposal(), quote(), NOW)
    assert not transport.sent
    gate.close()
    gate, transport = gate_at(tmp_path, config(orders_authorized=False))
    gate.reconcile(snapshot(), {}, NOW)
    with pytest.raises(DataError, match="not authorized"):
        gate.submit(proposal(), quote(), NOW)
    gate.close()


@pytest.mark.parametrize("accounts", [("U1234567",), ("DU9999999",), ("DU1234567", "U1234567"), ()])
def test_actual_managed_account_response_must_match_paper_allowlist(tmp_path, accounts):
    gate, transport = gate_at(tmp_path)
    transport.accounts = accounts
    with pytest.raises(DataError, match="verification failed"):
        gate.reconcile(snapshot(), {}, NOW)
    assert not transport.sent
    gate.close()


@pytest.mark.parametrize(
    "case",
    [
        "stale_quote",
        "future_quote",
        "delayed",
        "crossed",
        "stale_state",
        "stale_proposal",
        "expired",
        "short",
        "wrong_instrument",
        "loss",
        "overlimit",
    ],
)
def test_preflight_denies_invalid_or_risky_inputs(tmp_path, case):
    cfg = config()
    if case == "overlimit":
        cfg = replace(cfg, risk=replace(cfg.risk, max_notional=Decimal(100)))
    gate, transport = gate_at(tmp_path, cfg)
    state = snapshot(loss_today=Decimal(100)) if case == "loss" else snapshot()
    gate.reconcile(state, {}, NOW)
    p, q, now = proposal(), quote(), NOW
    if case == "stale_quote":
        q = quote(available_at=NOW - 3 * SECOND)
    elif case == "future_quote":
        q = quote(available_at=NOW + SECOND)
    elif case == "delayed":
        q = quote(realtime=False)
    elif case == "crossed":
        q = quote(bid=Decimal(101))
    elif case == "stale_state":
        now, p, q = NOW + 6 * SECOND, proposal(NOW + 6 * SECOND), quote(NOW + 6 * SECOND)
    elif case == "stale_proposal":
        p = proposal(NOW - 3 * SECOND)
    elif case == "expired":
        p = proposal(NOW - 61 * SECOND)
    elif case == "short":
        p = proposal(intent=Intent.SHORT)
    elif case == "wrong_instrument":
        p = proposal(instrument_id="OTHER.XNAS")
    with pytest.raises(DataError):
        gate.submit(p, q, now)
    assert not transport.sent
    gate.close()


def test_durable_reservation_duplicate_and_unknown_submission_never_resend(tmp_path):
    gate, transport = gate_at(tmp_path)
    gate.reconcile(snapshot(), {}, NOW)

    def durable_before_transport(order):
        with sqlite3.connect(tmp_path / "paper.sqlite") as db:
            assert db.execute(
                "SELECT status FROM orders WHERE id=?", (order.order_id,)
            ).fetchone() == ("PREPARED",)

    transport.before_submit = durable_before_transport
    transport.error = True
    with pytest.raises(DataError, match="outcome unknown"):
        gate.submit(proposal(), quote(), NOW)
    oid = transport.sent[0].order_id
    assert gate.orders()[oid] == "UNKNOWN"
    gate.close()
    gate, restarted = gate_at(tmp_path)
    with pytest.raises(DataError, match="halted"):
        gate.submit(proposal(), quote(), NOW)
    with pytest.raises(DataError, match="incomplete/unknown"):
        gate.reconcile(snapshot(), {}, NOW, resume=True)
    gate.reconcile(snapshot(), {oid: "REJECTED"}, NOW, resume=True)
    with pytest.raises(DataError, match="duplicate"):
        gate.submit(proposal(), quote(), NOW)
    assert not restarted.sent
    gate.close()


def test_partial_fill_cancel_race_ledger_and_restart(tmp_path):
    gate, transport = gate_at(tmp_path)
    gate.reconcile(snapshot(), {}, NOW)
    order = gate.submit(proposal(), quote(), NOW)
    with pytest.raises(DataError, match="pending"):
        gate.submit(proposal(NOW + SECOND), quote(NOW + SECOND), NOW + SECOND)
    gate.record_fill("exec-1", order.order_id, 1, Decimal("100.01"), Decimal("0.10"))
    gate.record_fill("exec-1", order.order_id, 1, Decimal("100.010"), Decimal("0.1"))
    assert gate._ledger() == (Decimal("9899.89"), 1)
    gate.kill()
    assert transport.cancelled == [order.order_id]
    gate.terminal(order.order_id, "CANCELLED")
    # Second fill arrives after the cancellation callback. The fill wins; no oversell/retry.
    gate.record_fill("exec-2", order.order_id, 1, Decimal("100.01"), Decimal("0.10"))
    assert gate.orders()[order.order_id] == "FILLED"
    gate.close()
    gate, _ = gate_at(tmp_path)
    state = snapshot(NOW + 3 * SECOND, cash=Decimal("9799.78"), position=2)
    with pytest.raises(DataError, match="explicit operator resume"):
        gate.reconcile(state, {order.order_id: "FILLED"}, NOW + 3 * SECOND)
    gate.reconcile(state, {order.order_id: "FILLED"}, NOW + 3 * SECOND, resume=True)
    exit_order = gate.submit(
        proposal(NOW + 3 * SECOND, Intent.FLAT), quote(NOW + 3 * SECOND), NOW + 3 * SECOND
    )
    assert exit_order.side == -1 and exit_order.quantity == 2
    gate.record_fill("exec-exit", exit_order.order_id, 2, Decimal(100), Decimal("0.20"))
    assert gate._ledger() == (Decimal("9999.58"), 0)
    gate.close()


def test_reconciliation_cash_mismatch_external_orders_and_writer_lock(tmp_path):
    gate, _ = gate_at(tmp_path)
    gate.reconcile(snapshot(), {}, NOW)
    with pytest.raises(DataError, match="active writer"):
        gate_at(tmp_path)
    with pytest.raises(DataError, match="do not reconcile"):
        gate.reconcile(snapshot(cash=Decimal(9999)), {}, NOW)
    with pytest.raises(DataError, match="unknown broker"):
        gate.reconcile(snapshot(), {"external": "ACK"}, NOW)
    gate.close()


def test_cancel_timeout_halts_until_broker_evidence(tmp_path):
    gate, transport = gate_at(tmp_path)
    gate.reconcile(snapshot(), {}, NOW)
    gate.submit(proposal(), quote(), NOW)
    transport.cancel_error = True
    with pytest.raises(DataError, match="cancel outcome unknown"):
        gate.kill()
    with pytest.raises(DataError, match="halted"):
        gate.submit(proposal(NOW + SECOND), quote(NOW + SECOND), NOW + SECOND)
    gate.close()


def test_filled_exposure_is_reserved_before_a_second_entry(tmp_path):
    cfg = config()
    cfg = replace(cfg, risk=replace(cfg.risk, max_quantity=Decimal(3)))
    gate, transport = gate_at(tmp_path, cfg)
    gate.reconcile(snapshot(), {}, NOW)
    order = gate.submit(proposal(), quote(), NOW)
    gate.record_fill("filled", order.order_id, 2, Decimal("100.01"), Decimal(0))
    now = NOW + 3 * SECOND
    gate.reconcile(
        snapshot(now, cash=Decimal("9799.98"), position=2), {order.order_id: "FILLED"}, now
    )
    with pytest.raises(DataError, match="quantity_exceeds_limit"):
        gate.submit(proposal(now), quote(now), now)
    assert len(transport.sent) == 1
    gate.close()


def test_rate_and_daily_attempt_limits_include_rejected_orders(tmp_path):
    cfg = config()
    cfg = replace(cfg, risk=replace(cfg.risk, max_entries_per_session=2))
    gate, transport = gate_at(tmp_path, cfg)
    gate.reconcile(snapshot(), {}, NOW)
    a = gate.submit(proposal(), quote(), NOW)
    gate.terminal(a.order_id, "REJECTED")
    reports = {a.order_id: "REJECTED"}
    gate.reconcile(snapshot(NOW + SECOND), reports, NOW + SECOND)
    with pytest.raises(DataError, match="rate limit"):
        gate.submit(proposal(NOW + SECOND), quote(NOW + SECOND), NOW + SECOND)
    gate.reconcile(snapshot(NOW + 3 * SECOND), reports, NOW + 3 * SECOND)
    b = gate.submit(proposal(NOW + 3 * SECOND), quote(NOW + 3 * SECOND), NOW + 3 * SECOND)
    gate.terminal(b.order_id, "REJECTED")
    reports[b.order_id] = "REJECTED"
    gate.reconcile(snapshot(NOW + 6 * SECOND), reports, NOW + 6 * SECOND)
    with pytest.raises(DataError, match="session_entry_limit_reached"):
        gate.submit(proposal(NOW + 6 * SECOND), quote(NOW + 6 * SECOND), NOW + 6 * SECOND)
    assert len(transport.sent) == 2
    gate.close()


def test_overfill_or_conflicting_execution_halts(tmp_path):
    gate, _ = gate_at(tmp_path)
    gate.reconcile(snapshot(), {}, NOW)
    order = gate.submit(proposal(), quote(), NOW)
    gate.record_fill("exec", order.order_id, 1, Decimal("100.01"), Decimal("0.10"))
    with pytest.raises(DataError, match="duplicate execution"):
        gate.record_fill("exec", order.order_id, 1, Decimal("100.00"), Decimal("0.10"))
    with pytest.raises(DataError, match="reserved quantity"):
        gate.record_fill("overfill", order.order_id, 2, Decimal("100.01"), Decimal(0))
    assert gate._ledger() == (Decimal("9899.89"), 1)
    gate.close()
