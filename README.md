<div align="center">

# Drift

Reproducible intraday research on NVDA shares in Python, on [NautilusTrader](https://nautilustrader.io).

![Python 3.12](https://img.shields.io/badge/python-3.12-3776AB?logo=python&logoColor=white)
![NautilusTrader 1.231.0](https://img.shields.io/badge/NautilusTrader-1.231.0-1f2937)
![Alpaca paper only](https://img.shields.io/badge/Alpaca-paper%20only-f5c518)
[![CI](https://github.com/antoniesuciu/drift/actions/workflows/ci.yml/badge.svg)](.github/workflows/ci.yml)

</div>

Drift is built around deterministic statistical rule strategies. It has a concurrent backtesting framework with persistent virtual portfolios, an offline market-data pipeline and a bounded Alpaca paper-trading runner. Every strategy goes through the same sizing, risk and execution layer.

> [!NOTE]
> **This is a research project, not a trading system or financial advice.** No strategy here has shown an edge after costs. Synthetic results only test the software, and the in-sample results describe a single sample.

## ✨ Features

| | |
|---|---|
| 📐 **Six statistical rules** | ITSM, ORB, VWAP and Bollinger reversion, short-term reversal, trend. One module each. |
| ⏱️ **Causal by construction** | Decisions see only completed, available candles. Fills land on the next eligible bar open. |
| 💸 **Explicit costs** | Commissions, minimums, sell-side regulatory fees, spread and slippage. No defaults. |
| 🔁 **Reproducible reports** | Each report records its resolved config plus data and result hashes. |
| 🧊 **Frozen research split** | Development 2020–2022, validation 2023 by opt-in, holdout 2024–2025 refused. |
| 📒 **Virtual portfolios** | Advance a portfolio window by window. Segmented equals uninterrupted, trade for trade. |
| ⚡ **Concurrent research runner** | Runs every strategy at once into a Parquet/DuckDB result store. |
| 🧯 **Bounded paper runner** | One ITSM session on Alpaca's paper endpoint behind a fail-closed SQLite gate. |

## 🚀 Quick start

You need Linux x86_64, CPython 3.12 and [uv](https://docs.astral.sh/uv/) 0.13.6. No GPU, Docker or broker application is required.

```sh
git clone https://github.com/antoniesuciu/drift.git
cd drift
uv sync --locked --extra ib
uv run drift smoke                    # engine check on three synthetic bars
uv run drift backtest --strategy orb  # synthetic demo backtest
```

## 🧭 How to use it

1. **Check the engine.** `drift smoke` runs NautilusTrader on three synthetic bars and prints a JSON summary with `"synthetic": true`.
2. **Run a demo.** `drift backtest --strategy <name>` runs a built-in synthetic setup. Names: `itsm`, `orb`, `vwap_reversion`, `bollinger_reversion`, `reversal`, `trend`.
3. **Take the config.** `drift backtest --strategy itsm --dump-config > cfg.json` prints the full demo configuration. Edit sizing, risk limits and costs there.
4. **Run your config.** `drift backtest --config cfg.json --output out/` writes `report.json`, `report.md` and `trades.csv`. Add `--json` to print the full report as JSON.
5. **Run research.** `drift research run --year 2020` runs every strategy concurrently. It needs the local archive (see below).
6. **Compare.** `drift research compare --sort sharpe` ranks the stored results.
7. **Keep a portfolio.** `drift portfolio create steady --strategy itsm`, then `drift portfolio advance steady --year 2020`.

A synthetic `orb` demo prints a report like this (trimmed):

```text
# Backtest report: orb-synthetic-demo

> Synthetic data: results validate software behavior only. They are not market observations and say nothing about profitability.

- Strategy: `orb`; instrument `SYNTH.XNAS`; capital 100000 USD
- Data: 30 sessions, 11700 one-minute candles, sha256 `38999afcb1778980`
- Config sha256 `738705ed4f932df9`; results sha256 `5c4f57d92ad805d8` (same inputs reproduce the same hash)
- Engine: NautilusTrader 1.231.0, 58 orders, 29 positions

| Metric | Value |
|---|---|
| trades | 29 |
| gross_pnl | -111.00 |
| commissions | 26.37 |
| net_pnl | -137.37 |
| max_drawdown | 165.91 |
...
Engine balance 99862.63 vs ledger 99862.63: difference 0.00 (OK)
```

The run exits non-zero if the engine and ledger balances do not reconcile.

## 📐 Strategies

Six rules live under `src/drift/strategies/rule/statistical/`, one module each. All of them read completed one-minute candles and emit versioned proposals. None of them can place an order itself.

| Strategy | Idea |
|---|---|
| `itsm` | Intraday time-series momentum: when the overnight-to-10:00 and 15:00–15:30 returns agree, trade the final half hour ([EXP-001](experiments/exp001_itsm/README.md)) |
| `orb` | Opening range breakout, with optional relative-volume, VWAP and range filters |
| `vwap_reversion` | Fades a stretch from session VWAP measured in standard deviations |
| `bollinger_reversion` | Fades a fresh close outside the Bollinger bands |
| `reversal` | Short-term reversal: fades the move of each completed 5–60 minute bucket |
| `trend` | Moving-average crossover trend following |

[STRATEGIES.md](docs/STRATEGIES.md) gives each rule's signal, entry, exit and parameters. The defaults are documented research choices, not tuned values.

## ⚙️ Backtest model

- **Fills.** A decision uses only candles that have completed and were available at the decision time. It fills at the open of the first bar that starts strictly after the decision plus order latency, adverse by the half-spread and slippage ([D-030](docs/DECISIONS.md)).
- **Exits.** Stops and targets are checked on completed bars. A bar that touches both counts as a stop.
- **Costs and sizing.** Commissions, minimums, sell-side regulatory fees, spread and slippage are all configured. Sizing, risk limits and costs have no defaults.
- **Reproducibility.** Each report records the resolved configuration plus data and result hashes. The same inputs reproduce the same hash.
- **Research split.** Development is 2020–2022. Validation is 2023, by explicit opt-in only. Holdout is 2024–2025, and backtests refuse to touch it ([D-034](docs/DECISIONS.md)).
- **Portfolios.** A portfolio can advance window by window. A segmented run equals one uninterrupted run, trade for trade.

## 🗄️ Historical data

Historical runs need a local archive of NVDA one-minute SIP bars. The repository contains no market data.

- [NVDA_HISTORY.md](docs/data/NVDA_HISTORY.md) covers how the archive is collected and checked.
- [BACKTESTING.md](docs/BACKTESTING.md) covers selection, costs, stored results and portfolios.
- You need your own Alpaca credentials to fetch data. The reader asks for explicit authorization and an explicit credential file. It never falls back between the SIP and IEX feeds.

## 🧪 Paper trading

`drift paper-*` drives a bounded ITSM session against Alpaca's **paper** endpoint only. It uses a fixed host, conservative one-share limits and a journaled SQLite safety gate. The gate fails closed on stale data, uncertain order state or reconciliation failure. Every connection and order run needs an explicit flag. See [PAPER_EXECUTION.md](docs/PAPER_EXECUTION.md).

> [!WARNING]
> Live trading is not implemented. No paper order has been submitted yet.

## 🔒 Safety

- Strategies only propose. The shared portfolio and risk controls decide whether anything becomes an order.
- Market data, credentials, account identifiers and generated results are kept out of Git.

## 📊 Status

> [!IMPORTANT]
> - **Done:** the six statistical rules, the NautilusTrader backtest engine and the research framework, all tested on synthetic data. The 2020–2025 NVDA SIP minute archive is collected and integrity-checked: 585,897 bars over 1,508 sessions.
> - **Pending:** formal data admission, a preregistered historical evaluation of ITSM (M3a), out-of-sample validation and supervised paper fills.

## 🗂️ Project layout

```text
src/drift/
  strategies/  proposal, market and calendar types; rule/statistical/ holds the six rules
  backtest/    strategy registry, config, sizing/risk/exit policy, Nautilus engine, reports
  research/    concurrent runner, Parquet/DuckDB result store, virtual portfolios
  data/        Alpaca equity reader and validation, monthly archive, synthetic pipeline
  execution/   Alpaca paper runner and safety gate (IBKR modules are inactive)
tests/         offline and synthetic, with no credentials
docs/          specifications, decisions and roadmap; docs/archive/ holds superseded research
experiments/   preregistered protocols
```

## 📚 Documents

| Document | Contents |
|---|---|
| [STRATEGIES.md](docs/STRATEGIES.md) | Every rule: signal, entry, exit, parameters |
| [BACKTESTING.md](docs/BACKTESTING.md) | Research runner, costs, result store, portfolios, known limits |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Boundaries, data flow and the proposal contract |
| [ROADMAP.md](docs/ROADMAP.md) · [REQUIREMENTS.md](REQUIREMENTS.md) | Milestones, gates and acceptance criteria |
| [DECISIONS.md](docs/DECISIONS.md) | Decision log with rationale |
| [COSTS_AND_PROVIDERS.md](docs/COSTS_AND_PROVIDERS.md) | Providers, brokers and the cost model |
| [GLOSSARY.md](GLOSSARY.md) · [AGENTS.md](AGENTS.md) | Vocabulary and the workflow for coding agents |

## ✅ Verify

Tests run offline with sockets blocked and need no credentials.

```sh
uv sync --locked --extra ib
uv run --locked --offline --extra ib ruff format --check .
uv run --locked --offline --extra ib ruff check .
uv run --locked --offline --extra ib mypy
uv run --locked --offline --extra ib pytest
```

[GitHub Actions](.github/workflows/ci.yml) runs the same checks.

---

<sub>The example output above comes from Drift's built-in synthetic demo data, not from market data.</sub>
