# Drift

Reproducible intraday research on NVDA shares in Python on [NautilusTrader](https://nautilustrader.io). Drift is built around deterministic statistical rule strategies. It has a concurrent backtesting framework with persistent virtual portfolios, an offline market-data pipeline and a bounded Alpaca paper-trading runner. Every strategy goes through the same sizing, risk and execution layer.

> **This is a research project, not a trading system or financial advice.** No strategy here has shown an edge after costs. Synthetic results only test the software, and the in-sample results describe a single sample.

## Strategies

Six rules live under `src/drift/strategies/rule/statistical/`, one module each. All of them read completed one-minute candles and emit versioned proposals; none of them can place an order itself.

| Strategy | Idea |
|---|---|
| `itsm` | Intraday time-series momentum: when the overnight-to-10:00 and 15:00–15:30 returns agree, trade the final half hour ([EXP-001](experiments/exp001_itsm/README.md)) |
| `orb` | Opening range breakout, with optional relative-volume, VWAP and range filters |
| `vwap_reversion` | Fades a stretch from session VWAP measured in standard deviations |
| `bollinger_reversion` | Fades a fresh close outside the Bollinger bands |
| `reversal` | Short-term reversal: fades the move of each completed 5–60 minute bucket |
| `trend` | Moving-average crossover trend following |

[STRATEGIES.md](docs/STRATEGIES.md) gives each rule's signal, entry, exit and parameters. The defaults are documented research choices, not tuned values.

## How it works

- **Causal by construction.** A decision uses only candles that have completed and were available at the decision time. It fills at the open of the first bar that starts strictly after the decision plus order latency, adverse by the half-spread and slippage ([D-030](docs/DECISIONS.md)). Stops and targets are checked on completed bars, and a bar that touches both counts as a stop.
- **Explicit costs.** Commissions, minimums, sell-side regulatory fees, spread and slippage are all configured. Sizing, risk limits and costs have no defaults.
- **Reproducible.** Each report records the resolved configuration plus data and result hashes, and the same inputs reproduce the same hash.
- **Frozen research split.** Development is 2020–2022, validation is 2023 (explicit opt-in only) and holdout is 2024–2025, which backtests refuse to touch ([D-034](docs/DECISIONS.md)).
- **Virtual portfolios.** A portfolio can advance window by window, and a segmented run equals one uninterrupted run, trade for trade.

## Install and check

You need Linux x86_64, CPython 3.12 and [uv](https://docs.astral.sh/uv/) 0.13.6. No GPU, Docker or broker application is required, and tests run offline with sockets blocked.

```sh
uv sync --locked --extra ib
uv run --locked --offline --extra ib ruff format --check .
uv run --locked --offline --extra ib ruff check .
uv run --locked --offline --extra ib mypy
uv run --locked --offline --extra ib pytest
```

[GitHub Actions](.github/workflows/ci.yml) runs the same checks.

## Run

```sh
drift smoke                                      # engine check on three synthetic bars
drift backtest --strategy orb                    # synthetic demo for any strategy
drift backtest --strategy itsm --dump-config > cfg.json
drift backtest --config cfg.json --output out/   # report.json, report.md, trades.csv
drift research run --year 2020                   # every strategy, concurrently (needs the local archive)
drift research compare --sort sharpe
drift portfolio create steady --strategy itsm
drift portfolio advance steady --year 2020
```

Historical runs need a local archive of NVDA one-minute SIP bars. The repository contains no market data. [NVDA_HISTORY.md](docs/data/NVDA_HISTORY.md) covers how the archive is collected and checked, and [BACKTESTING.md](docs/BACKTESTING.md) covers selection, costs, stored results and portfolios. You need your own Alpaca credentials to fetch data. The reader asks for explicit authorization and an explicit credential file, and it never falls back between the SIP and IEX feeds.

## Paper trading

`drift paper-*` drives a bounded ITSM session against Alpaca's **paper** endpoint only. It uses a fixed host, conservative one-share limits and a journaled SQLite safety gate that fails closed on stale data, uncertain order state or reconciliation failure. Every connection and order run needs an explicit flag. Live trading is not implemented. See [PAPER_EXECUTION.md](docs/PAPER_EXECUTION.md).

## Layout

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

## Documents

| Document | Contents |
|---|---|
| [STRATEGIES.md](docs/STRATEGIES.md) | Every rule: signal, entry, exit, parameters |
| [BACKTESTING.md](docs/BACKTESTING.md) | Research runner, costs, result store, portfolios, known limits |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Boundaries, data flow and the proposal contract |
| [ROADMAP.md](docs/ROADMAP.md) · [REQUIREMENTS.md](REQUIREMENTS.md) | Milestones, gates and acceptance criteria |
| [DECISIONS.md](docs/DECISIONS.md) | Decision log with rationale |
| [COSTS_AND_PROVIDERS.md](docs/COSTS_AND_PROVIDERS.md) | Providers, brokers and the cost model |
| [GLOSSARY.md](GLOSSARY.md) · [AGENTS.md](AGENTS.md) | Vocabulary and the workflow for coding agents |

## Status

- **Done:** the six statistical rules, the NautilusTrader backtest engine and the research framework, all tested on synthetic data. The 2020–2025 NVDA SIP minute archive is collected and integrity-checked: 585,897 bars over 1,508 sessions.
- **Pending:** formal data admission, a preregistered historical evaluation of ITSM (M3a), out-of-sample validation and supervised paper fills. No paper order has been submitted yet.

## Safety

Strategies only propose. The shared portfolio and risk controls decide whether anything becomes an order. Market data, credentials, account identifiers and generated results are kept out of Git.
