# Quant Trading Lab

Reproducible quantitative trading research in Python on NautilusTrader: deterministic rule strategies, a backtest runner and an offline market-data pipeline, with shared risk controls between every strategy and any order. The package is `quantlab`.

**Scope:** NVDA shares, Alpaca historical SIP data, IBKR as the eventual execution broker. Crypto is deferred; ML and LLM agents are future families; relative strength waits for benchmark data.

**Status** ([roadmap](docs/ROADMAP.md) has the gates):
- **Done:** offline foundation; synthetic MES data pipeline with a native Parquet catalog and replay; seven rule strategies (ITSM, opening range breakout, VWAP and Bollinger mean reversion, short-term reversal, trend following, candlestick patterns); a synthetic-data backtest runner.
- **Pending:** real NVDA data admission (NVDA-001–010), any historical research result, broker connectivity, paper trading. No real market data has entered the project.
- Synthetic results validate software behavior only. Nothing here is evidence of profitability.

## Install and check

Ubuntu 24.04 x86_64, CPython 3.12, [uv 0.13.6](https://docs.astral.sh/uv/getting-started/installation/) (`pipx install uv==0.13.6`). No GPU, Docker or broker application is needed. The first sync needs network or a populated uv cache; everything after runs offline, and pytest blocks sockets.

```sh
uv sync --locked --extra ib
uv run --locked --offline --extra ib ruff format --check .
uv run --locked --offline --extra ib ruff check .
uv run --locked --offline --extra ib mypy
uv run --locked --offline --extra ib pytest
uv lock --check --offline && uv pip check
```

[GitHub Actions](.github/workflows/ci.yml) runs the same checks on pushes to `main` and pull requests. Keep `uv.lock` committed and use `--locked`.

## Run

```sh
quantlab backtest --strategy orb                    # itsm | candlestick | orb | vwap_reversion |
                                                    # bollinger_reversion | reversal | trend
quantlab backtest --strategy itsm --dump-config > cfg.json
quantlab backtest --config cfg.json --output out/   # report.json, report.md, trades.csv
quantlab smoke                                      # engine check on three synthetic bars
quantlab data-demo --output data/offline-demo       # ingest and replay synthetic MES data
```

A configuration fixes the instrument, capital, seeded synthetic data, execution costs, sizing, risk limits and strategy parameters. Costs, sizing and risk have **no defaults**; every report records the resolved configuration plus data and result hashes, and the same inputs reproduce the same hash. Execution goes through NautilusTrader: a decision fills at the open of the first bar that starts strictly after the decision plus order latency, adverse by the configured half-spread and slippage ([D-030](docs/DECISIONS.md)).

## Layout

```text
src/quantlab/
  data/        offline MES pipeline: DBN decoding, validation, native Parquet catalog, replay
  strategies/  shared market/proposal/calendar types
    rule/statistical/   itsm, orb, vwap_reversion, bollinger_reversion, reversal, trend
    rule/candlestick/   patterns, filters, policy
    ml/  llm/           deferred families (docstring only)
  backtest/    config, synthetic data, sizing/risk/exit policy, Nautilus engine, reports
  smoke.py  time.py  __main__.py
tests/         offline, synthetic, no credentials
docs/          specifications and decisions; docs/archive/ holds superseded research
experiments/   preregistered protocols (EXP-001)
```

## Documents

| Document | Contents |
|---|---|
| [REQUIREMENTS.md](REQUIREMENTS.md) | Requirement IDs and measurable acceptance criteria |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Milestones M0–M10, status and exit gates |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Decision log (D-001…) |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Boundaries, data flow, agent families and the proposal contract |
| [docs/STRATEGIES.md](docs/STRATEGIES.md) | Every rule strategy: signal, entry, exit, parameters |
| [docs/data/NVDA_DATA_PLAN.md](docs/data/NVDA_DATA_PLAN.md) | NVDA/Alpaca admission plan and gates |
| [docs/data/PIPELINE.md](docs/data/PIPELINE.md) | The implemented synthetic pipeline: formats, storage, limits |
| [docs/COSTS_AND_PROVIDERS.md](docs/COSTS_AND_PROVIDERS.md) | Providers, brokers and cost model |
| [docs/M1_FOUNDATION.md](docs/M1_FOUNDATION.md) | Verified runtime, dependency decision and API boundaries |
| [experiments/exp001_itsm](experiments/exp001_itsm/README.md) | EXP-001 protocol |
| [GLOSSARY.md](GLOSSARY.md) · [AGENTS.md](AGENTS.md) · [docs/PROJECT_MEMORY.md](docs/PROJECT_MEMORY.md) | Vocabulary, agent workflow, Obsidian memory |
| [docs/archive](docs/archive/README.md) | M0 audit, MES-era data research, Gemini reports (checksummed) |

## Safety

Agents emit proposals; only shared portfolio and risk controls authorize order intents. Data, model artifacts, credentials and generated results stay out of Git; small synthetic fixtures are tracked. Paid services, broker connections, paper orders and live trading each need explicit authorization; a milestone is never one.
