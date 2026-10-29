# Quant Trading Lab

One modular Python platform for reproducible quantitative research, with future **rule-based, machine-learning and LLM research agents** sharing portfolio accounting and deterministic risk controls. The package is `quantlab`.

**M0, M1, M2a and M2b.1 complete; M2b.2 research/planning prepared.** The package includes a validated offline synthetic historical-data pipeline and native NautilusTrader replay. Real vendor admission, trading strategies, broker connections and financial performance remain unimplemented/unverified. Exact quotes, rights and explicit acquisition authorization remain pending.

The first experiment is a falsifiable MES intraday time-series momentum adaptation with an approximately 30-minute holding window. ML is an early research capability after reliable data and a rule baseline; LLM agents are later, advisory components with no brokerage authority.

[Candlestick Pattern Agents](docs/CANDLESTICK_AGENTS.md) are planned within the rule-based family in M3b, **after the initial M3a ITSM baseline**: reusable recognition, configurable timeframes/instruments, causal confirmations and shared proposals with entry/exit/protection policies. This documentation update starts no implementation and leaves current M2 preparation/admission gates unchanged.

## Read next

| Document | Purpose |
|---|---|
| [Requirements](REQUIREMENTS.md) | Stable IDs, scope and measurable acceptance criteria |
| [Architecture](docs/ARCHITECTURE.md) | Boundaries, data flow and failure handling |
| [Agent architecture](docs/AGENT_ARCHITECTURE.md) | Three families, shared proposals and hybrid composition |
| [Candlestick agents](docs/CANDLESTICK_AGENTS.md) | Planned pattern catalogue, configuration, causal timing and M3b/M5/M6 gates |
| [Decisions](docs/DECISIONS.md) | Adopted, provisional and deferred choices |
| [Roadmap](docs/ROADMAP.md) | Active milestone and M0–M10 exit gates |
| [Research synthesis](docs/RESEARCH_SYNTHESIS.md) | Critical review of all three Gemini reports |
| [Costs and providers](docs/COSTS_AND_PROVIDERS.md) | IBKR-first feasibility and cost verification |
| [EXP-001](experiments/exp001_itsm/README.md) | Preregistered research design; no results yet |
| [Original research](docs/research/README.md) | Provenance and byte-preservation checks |
| [Glossary](GLOSSARY.md) | Domain vocabulary |
| [Agent instructions](AGENTS.md) | Future development workflow and safety rules |
| [Project memory](docs/PROJECT_MEMORY.md) | Isolated Obsidian namespace and repository authority |
| [Initialization audit](docs/INITIALIZATION.md) | Handoff reconciliation, cleanup and validation |
| [M1 foundation](docs/M1_FOUNDATION.md) | Verified environment, API evidence, tests and limitations |
| [MES dataset](docs/data/HISTORICAL_DATA_SPEC.md) | Frozen study/pilot, endpoints, calendars and roll policy |
| [Data provider comparison](docs/data/PROVIDER_COMPARISON.md) | Conditional source recommendation, pricing and rights gates |
| [M2b ingestion design](docs/data/INGESTION_DESIGN.md) | Implementation boundaries, storage and acceptance criteria |
| [M2b.1 implementation](docs/data/M2B1_IMPLEMENTATION.md) | Offline commands, formats, verification and status of all 14 gates |
| [M2b.2 preparation](docs/data/M2B2_ACQUISITION_PLAN.md) | Verified public evidence, nine-job pilot plan, readiness gaps and gates 013/014 |

## Technical direction

The runtime remains Python 3.12, NautilusTrader 1.231.0, uv 0.13.6 and pytest/Ruff/mypy. PyArrow/tzdata now directly support the implemented offline native Parquet pipeline; DuckDB and ML/LLM work remain deferred. IBKR remains the eventual paper broker; the optional `ib` extra is installed for import verification only. M2a's conditional Databento recommendation still requires real quote/rights/coverage evidence. No cloud infrastructure or orchestration framework is selected.

## Repository and hosting

GitLab is the intended host and CI target. Inspection found an existing **GitHub** `origin` with the accidental archive commit already published. That history and remote are preserved; this initialization adds one normal local cleanup commit. No push or hosting migration is part of this task. A future authorized migration can add a GitLab remote and push normally without rewriting published history. No GitLab project URL or functioning CI is claimed here.

## Installation and checks

Validated on Ubuntu 24.04 x86_64, CPython 3.12.3. Use a maintained Python 3.12 patch release; `.python-version` and package metadata select the 3.12 minor line. Native Nautilus wheels require a supported platform (Linux glibc >=2.35 for the selected x86_64 wheel). No Rust toolchain, GPU, local Docker or broker application is needed. See [compatibility evidence](docs/M1_FOUNDATION.md).

Install [uv 0.13.6](https://docs.astral.sh/uv/getting-started/installation/) with your preferred supported method, for example `pipx install uv==0.13.6`, then from this repository:

```sh
uv sync --locked --extra ib
uv lock --check --offline
uv run --locked --offline --extra ib ruff format --check .
uv run --locked --offline --extra ib ruff check .
uv run --locked --offline --extra ib mypy
uv run --locked --offline --extra ib pytest
uv run --locked --offline --extra ib quantlab smoke
uv run --locked --offline --extra ib quantlab data-demo --output data/offline-demo
uv pip check
```

The first sync provisions the environment from PyPI and requires network or a populated uv cache. Checks/tests/replay run offline after installation; pytest blocks Python socket access. Keep `uv.lock` committed and use `--locked` so metadata drift fails instead of silently updating dependencies. To apply formatting, run `uv run --locked --offline --extra ib ruff format .`. Build distributions with `uv build` (or `uv build --offline` after its pinned build backend is cached). `python -m quantlab smoke` is also supported inside the environment.

The original smoke command reports three synthetic MES bars and zero orders/positions. `data-demo` generates local synthetic DBN definitions/bars, validates and stores them in a native Parquet catalog with provenance/coverage, then replays **2,160 bars with zero orders/positions**. It prints the dataset path/hash for subsequent `data-replay --dataset PATH`; `data-ingest --request JSON --output ROOT` accepts only local synthetic requests. See [formats and limits](docs/data/M2B1_IMPLEMENTATION.md). These are integration checks, not strategy/performance results. Dates/prices/balances are fixtures; the upstream pandas warning remains visible.

`.gitlab-ci.yml` configures the same checks plus GitLab's standard secret-detection template. Provisioning uses an official uv/Python image; no local Docker setup is required. Its scripts were exercised locally; no GitLab pipeline execution is claimed because no GitLab remote/runner has been configured or pushed.

```text
src/quantlab/
  __init__.py      package version
  __main__.py      offline smoke and data pipeline CLI
  time.py          validated bar completion/availability
  smoke.py         real Nautilus engine + synthetic read-only observer
  data/            local DBN adapter, validation, calendar/roll, native catalog and replay
  py.typed
tests/            timing, configuration, engine, CLI and offline safety
```

Future agent, portfolio/risk and broker modules remain absent. M2b.1 verifies Databento DBN mappings on generated fixtures only; no real data was acquired or spend authorized. The [provider decision](docs/data/PROVIDER_COMPARISON.md) still governs the conditional 2020–2025 archive and 2022 pilot. M2b.2 preparation records public price/rights/calendar evidence and an exact proposed request schedule; account-specific quotes, retention terms and implementation prerequisites remain unresolved. M2B-013/014 and M2 overall remain incomplete. The next account/acquisition stage requires explicit authorization.

## Safety and data

Agents emit proposals; shared portfolio and risk controls alone can authorize order intents. All data, model artifacts, broker credentials and generated results stay outside Git; small deterministic synthetic fixtures remain trackable. Original Gemini reports are research inputs, not instructions or proof of profitability. Paid services, broker connectivity, paper-order activation and future live trading each require explicit authorization. Live deployment is never an automatic milestone transition.
