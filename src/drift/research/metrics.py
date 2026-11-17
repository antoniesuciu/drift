"""Comparable performance metrics, for one run or a whole portfolio history.

A metric is a function of a `Frame` returning named floats; `@metric` adds one, and it then
reaches stored results and the `comparison` view with no schema change. Trade statistics reuse
`backtest.report`. Risk is measured on mark-to-market session closes at zero risk-free rate, so
it sees open-trade losses that realized PnL hides. Values describe a sample: an annualized
Sharpe from a few months is noise, which is why its standard error sits beside it.
"""

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from math import sqrt
from statistics import fmean, stdev
from typing import Any

import pyarrow as pa

from drift.backtest.report import Trade, metrics

_SESSIONS_PER_YEAR = 252


@dataclass(frozen=True, slots=True)
class Frame:
    capital: Decimal  # equity before the first bar
    trades: tuple[Trade, ...]
    closes: tuple[float, ...]  # the last equity of each session
    max_drawdown: Decimal  # mark-to-market, from `equity`
    max_drawdown_pct: float
    window_ns: int  # cash-session time covered, for exposure


Metric = Callable[[Frame], dict[str, float | None]]
_METRICS: list[Metric] = []


def metric(function: Metric) -> Metric:
    _METRICS.append(function)
    return function


def compute(frame: Frame) -> dict[str, float | None]:
    return {name: value for function in _METRICS for name, value in function(frame).items()}


def metric_names() -> tuple[str, ...]:
    """What `compute` reports, so views need no list of their own."""
    return tuple(compute(Frame(Decimal(1), (), (), Decimal(0), 0.0, 1)))


def _ints(table: pa.Table, column: str) -> list[int]:
    result: list[int] = table.column(column).cast(pa.int64()).to_pylist()
    return result


def frame_of(trades: pa.Table, equity: pa.Table, capital: Decimal, window_ns: int) -> Frame:
    """Build a frame from stored tables, so a run and a portfolio share one calculation."""
    rows = trades.drop_columns(["entry_ts", "exit_ts"]).to_pylist()
    entries, exits = _ints(trades, "entry_ts"), _ints(trades, "exit_ts")
    ledger = tuple(
        Trade(
            r["number"],
            r["side"],
            r["quantity"],
            entry,
            exit_,
            r["entry_price"],
            r["exit_price"],
            r["gross_pnl"],
            r["commission"],
            r["net_pnl"],
            r["exit_reason"],
            r["signal"],
            r["proposal_id"],
        )
        for r, entry, exit_ in zip(rows, entries, exits, strict=True)
    )
    closes: dict[str, Decimal] = {}
    days, values = equity.column("session_date").to_pylist(), equity.column("equity").to_pylist()
    closes.update(zip(days, values, strict=True))
    drawdown = max(equity.column("drawdown").to_pylist(), default=Decimal(0))
    percent = max(equity.column("drawdown_pct").to_pylist(), default=0.0)
    return Frame(
        capital, ledger, tuple(float(v) for v in closes.values()), drawdown, percent, window_ns
    )


def _float(value: Any) -> float | None:
    return None if value is None else float(value)


@metric
def trading(frame: Frame) -> dict[str, float | None]:
    report = metrics(list(frame.trades), frame.capital, frame.window_ns)
    keys = (
        "trades",
        "long_trades",
        "short_trades",
        "gross_pnl",
        "commissions",
        "net_pnl",
        "net_return",
        "win_rate",
        "average_win",
        "average_loss",
        "profit_factor",
        "expectancy_per_trade",
        "average_holding_seconds",
        "exposure_fraction",
    )
    return {key: _float(report[key]) for key in keys}


@metric
def risk(frame: Frame) -> dict[str, float | None]:
    start = float(frame.capital)
    returns = [b / a - 1 for a, b in zip((start, *frame.closes), frame.closes, strict=False)]
    result: dict[str, float | None] = dict.fromkeys(
        ("volatility", "sharpe", "sharpe_standard_error", "sortino", "annual_return", "calmar")
    )
    result |= {
        "max_drawdown": float(frame.max_drawdown),
        "max_drawdown_pct": frame.max_drawdown_pct,
        "best_session": max(returns, default=None),
        "worst_session": min(returns, default=None),
    }
    if not returns:
        return result
    annual = _SESSIONS_PER_YEAR
    total = frame.closes[-1] / start
    if total > 0:
        annual_return = total ** (annual / len(returns)) - 1
        result["annual_return"] = annual_return
        if frame.max_drawdown_pct > 0:
            result["calmar"] = annual_return / frame.max_drawdown_pct
    if len(returns) < 2:
        return result
    mean, deviation = fmean(returns), stdev(returns)
    result["volatility"] = deviation * sqrt(annual)
    if deviation > 0:
        ratio = mean / deviation
        result["sharpe"] = ratio * sqrt(annual)
        # Lo (2002), i.i.d. returns: serial correlation would change it.
        result["sharpe_standard_error"] = sqrt((1 + ratio**2 / 2) / len(returns) * annual)
    downside = sqrt(sum(min(r, 0.0) ** 2 for r in returns) / len(returns))
    if downside > 0:
        result["sortino"] = mean / downside * sqrt(annual)
    return result


@metric
def frequency(frame: Frame) -> dict[str, float | None]:
    sessions = len(frame.closes)
    count = len(frame.trades)
    notional = sum(float(t.quantity * t.entry_price) for t in frame.trades)
    return {
        "sessions": float(sessions),
        "trades_per_session": count / sessions if sessions else None,
        "average_trade_notional": notional / count if count else None,
    }
