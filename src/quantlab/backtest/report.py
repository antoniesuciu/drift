"""Trade ledger, performance metrics and the reproducible backtest report.

Metrics are computed from executed fills only. `results_sha256` covers every outcome (trades,
proposals, rejections, metrics, reconciliation) and deliberately excludes wall-clock time,
run ids and software versions, which are reported separately: same config and data give the
same hash.
"""

import csv
import io
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from quantlab.data.model import SECOND, DataError, canonical, digest

SYNTHETIC_NOTICE = (
    "Synthetic data: results validate software behavior only. They are not market "
    "observations and say nothing about profitability."
)
CONVENTIONS = (
    "Fills occur at the open of the first 1-minute bar starting strictly after decision time "
    "plus order latency, adverse by the configured half-spread and slippage; the engine "
    "(NautilusTrader) performs matching, commissions, positions and account accounting.",
    "Stops and targets are checked on completed bars; the exit fills at the next eligible "
    "open, so gaps and delay are paid for. A bar touching both levels counts as a stop.",
    "Equity curve and drawdown use realized closed-trade PnL; open-trade marks are not modeled.",
)


@dataclass(frozen=True, slots=True)
class Trade:
    number: int
    side: str
    quantity: Decimal
    entry_ts: int
    exit_ts: int
    entry_price: Decimal
    exit_price: Decimal
    gross_pnl: Decimal
    commission: Decimal
    net_pnl: Decimal
    exit_reason: str
    signal: str
    proposal_id: str
    flags: tuple[str, ...] = ()

    @property
    def held_seconds(self) -> int:
        return (self.exit_ts - self.entry_ts) // SECOND

    def row(self) -> dict[str, Any]:
        return {
            "number": self.number,
            "side": self.side,
            "quantity": str(self.quantity),
            "entry_ts": self.entry_ts,
            "exit_ts": self.exit_ts,
            "held_seconds": self.held_seconds,
            "entry_price": str(self.entry_price),
            "exit_price": str(self.exit_price),
            "gross_pnl": str(self.gross_pnl),
            "commission": str(self.commission),
            "net_pnl": str(self.net_pnl),
            "exit_reason": self.exit_reason,
            "signal": self.signal,
            "proposal_id": self.proposal_id,
            "flags": list(self.flags),
        }


def _ratio(a: Decimal, b: Decimal) -> str | None:
    return None if b == 0 else str(a / b)


def metrics(trades: list[Trade], capital: Decimal, exposure_window_ns: int) -> dict[str, Any]:
    wins = [t for t in trades if t.net_pnl > 0]
    losses = [t for t in trades if t.net_pnl < 0]
    net = sum((t.net_pnl for t in trades), Decimal(0))
    gross = sum((t.gross_pnl for t in trades), Decimal(0))
    fees = sum((t.commission for t in trades), Decimal(0))
    won = sum((t.net_pnl for t in wins), Decimal(0))
    lost = -sum((t.net_pnl for t in losses), Decimal(0))
    equity = peak = capital
    drawdown = Decimal(0)
    drawdown_pct = Decimal(0)
    for t in trades:
        equity += t.net_pnl
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
        drawdown_pct = max(drawdown_pct, (peak - equity) / peak)
    count = len(trades)
    held = sum(t.held_seconds for t in trades) * SECOND
    reasons: dict[str, int] = {}
    for t in trades:
        reasons[t.exit_reason] = reasons.get(t.exit_reason, 0) + 1
    return {
        "trades": count,
        "long_trades": sum(t.side == "LONG" for t in trades),
        "short_trades": sum(t.side == "SHORT" for t in trades),
        "gross_pnl": str(gross),
        "commissions": str(fees),
        "net_pnl": str(net),
        "net_return": str(net / capital),
        "ending_equity": str(capital + net),
        "win_rate": _ratio(Decimal(len(wins)), Decimal(count)),
        "average_win": _ratio(won, Decimal(len(wins))),
        "average_loss": _ratio(-lost, Decimal(len(losses))),
        "profit_factor": _ratio(won, lost),
        "expectancy_per_trade": _ratio(net, Decimal(count)),
        "max_drawdown": str(drawdown),
        "max_drawdown_pct": str(drawdown_pct),
        "average_holding_seconds": _ratio(Decimal(held // SECOND), Decimal(count)),
        "exposure_fraction": _ratio(Decimal(held), Decimal(exposure_window_ns)),
        "exit_reasons": dict(sorted(reasons.items())),
    }


@dataclass(frozen=True, slots=True)
class BacktestResult:
    config: dict[str, Any]
    config_sha256: str
    data_sha256: str
    data_summary: dict[str, Any]
    software: dict[str, Any]
    engine: dict[str, Any]
    trades: tuple[Trade, ...]
    proposals: tuple[dict[str, Any], ...]
    rejections: tuple[dict[str, Any], ...]
    metrics: dict[str, Any]
    reconciliation: dict[str, Any]
    open_at_end: dict[str, Any] | None

    def outcomes(self) -> dict[str, Any]:
        return {
            "trades": [t.row() for t in self.trades],
            "proposals": list(self.proposals),
            "rejections": list(self.rejections),
            "metrics": self.metrics,
            "reconciliation": self.reconciliation,
            "open_at_end": self.open_at_end,
        }

    @property
    def results_sha256(self) -> str:
        return digest(canonical(self.outcomes()))

    def to_dict(self) -> dict[str, Any]:
        return {
            "synthetic": True,
            "notice": SYNTHETIC_NOTICE,
            "config": self.config,
            "config_sha256": self.config_sha256,
            "data_sha256": self.data_sha256,
            "data": self.data_summary,
            "software": self.software,
            "engine": self.engine,
            "results_sha256": self.results_sha256,
            **self.outcomes(),
        }

    def trades_csv(self) -> str:
        rows = [t.row() for t in self.trades]
        out = io.StringIO()
        names = list(rows[0]) if rows else list(Trade.__dataclass_fields__)
        writer = csv.DictWriter(out, fieldnames=names, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row | {"flags": ";".join(row["flags"])})
        return out.getvalue()

    def markdown(self) -> str:
        m = self.metrics
        s = self.config["strategy"]
        counts: dict[str, int] = {}
        for p in self.proposals:
            counts[p["intent"]] = counts.get(p["intent"], 0) + 1
        lines = [
            f"# Backtest report: {self.config['name']}",
            "",
            f"> {SYNTHETIC_NOTICE}",
            "",
            f"- Strategy: `{s['name']}`; instrument `{self.data_summary['instrument']}`; "
            f"capital {self.config['capital']} USD",
            f"- Data: {self.data_summary['sessions']} sessions, "
            f"{self.data_summary['candles']} one-minute candles, sha256 `{self.data_sha256[:16]}`",
            f"- Config sha256 `{self.config_sha256[:16]}`; results sha256 "
            f"`{self.results_sha256[:16]}` (same inputs reproduce the same hash)",
            f"- Engine: NautilusTrader {self.software['nautilus']}, "
            f"{self.engine['orders']} orders, {self.engine['positions']} positions",
            "",
            "## Performance",
            "",
            "| Metric | Value |",
            "|---|---|",
        ]
        for key, value in m.items():
            if key != "exit_reasons":
                lines.append(f"| {key} | {value if value is not None else 'n/a'} |")
        lines += [
            "",
            f"Exit reasons: {m['exit_reasons'] or 'none'}",
            f"Proposals: {len(self.proposals)} ({counts or 'none'}); "
            f"risk/engine rejections: {len(self.rejections)}",
            "",
            "## Reconciliation",
            "",
            f"Engine balance {self.reconciliation['engine_balance']} vs ledger "
            f"{self.reconciliation['ledger_balance']}: difference "
            f"{self.reconciliation['difference']} "
            f"({'OK' if self.reconciliation['ok'] else 'MISMATCH'})",
        ]
        if self.open_at_end:
            lines += ["", f"**Position still open at the end of data:** {self.open_at_end}"]
        lines += ["", "## Trades", ""]
        if self.trades:
            lines += [
                "| # | side | qty | entry | exit | entry px | exit px | net pnl | exit reason |",
                "|---|---|---|---|---|---|---|---|---|",
            ]
            for t in self.trades:
                lines.append(
                    f"| {t.number} | {t.side} | {t.quantity} | {t.entry_ts} | {t.exit_ts} | "
                    f"{t.entry_price} | {t.exit_price} | {t.net_pnl} | {t.exit_reason} |"
                )
        else:
            lines.append("No trades executed.")
        lines += ["", "## Conventions and limits", ""]
        lines += [f"- {c}" for c in CONVENTIONS]
        return "\n".join(lines) + "\n"

    def write(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        outputs = {
            "report.json": json.dumps(self.to_dict(), sort_keys=True, indent=2) + "\n",
            "report.md": self.markdown(),
            "trades.csv": self.trades_csv(),
        }
        if any((directory / name).is_symlink() for name in outputs):
            raise DataError("report output must not be a symlink")
        for name, text in outputs.items():
            (directory / name).write_text(text)
