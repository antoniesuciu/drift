# Quant Trading Lab

One modular Python platform for reproducible quantitative research, with future **rule-based, machine-learning and LLM research agents** sharing portfolio accounting and deterministic risk controls. The package is `quantlab`.

**M0, M1, M2a and M2b.1 complete; M2b.2 research/planning prepared.** The package includes a validated offline synthetic historical-data pipeline and native NautilusTrader replay. Real vendor admission, trading strategies, broker connections and financial performance remain unimplemented/unverified. NVDA source rights/access, real-data admission and acquisition authorization remain pending; the earlier MES acquisition plans are historical.

**Confirmed scope, 2026-10-30: NVDA shares, Alpaca historical SIP data, IBKR execution; crypto deferred.** The first planned experiment is a falsifiable NVDA intraday momentum adaptation with an approximately 30-minute holding window. ML/LLM model selection waits until rule research is evaluated. Data, instrument metadata, strategies and execution adapters remain independently extensible through small interfaces; NVDA is the first configuration, not a platform-wide constant. See the [active data plan](docs/data/NVDA_DATA_PLAN.md).

[Candlestick Pattern Agents](docs/CANDLESTICK_AGENTS.md) are planned within the rule-based family in M3b, **after the initial M3a ITSM baseline**: reusable recognition, configurable timeframes/instruments, causal confirmations and shared proposals with entry/exit/protection policies. Candlestick implementation remains pending; current M2 preparation/admission follows the active NVDA plan.

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
| [Costs and providers](docs/COSTS_AND_PROVIDERS.md) | Alpaca history, IBKR execution and stock cost discipline |
| [EXP-001](experiments/exp001_itsm/README.md) | Preregistered research design; no results yet |
| [Original research](docs/research/README.md) | Provenance and byte-preservation checks |
| [Glossary](GLOSSARY.md) | Domain vocabulary |
| [Agent instructions](AGENTS.md) | Future development workflow and safety rules |
| [Project memory](docs/PROJECT_MEMORY.md) | Isolated Obsidian namespace and repository authority |
| [Initialization audit](docs/INITIALIZATION.md) | Handoff reconciliation, cleanup and validation |
| [M1 foundation](docs/M1_FOUNDATION.md) | Verified environment, API evidence, tests and limitations |
| [Active NVDA data plan](docs/data/NVDA_DATA_PLAN.md) | Alpaca/NVDA scope, fixed split, modular interfaces and pending admission gates |
| [Earlier MES dataset](docs/data/HISTORICAL_DATA_SPEC.md) | Historical specification supporting unchanged synthetic MES evidence |
| [Data provider comparison](docs/data/PROVIDER_COMPARISON.md) | Conditional source recommendation, pricing and rights gates |
| [M2b ingestion design](docs/data/INGESTION_DESIGN.md) | Implementation boundaries, storage and acceptance criteria |
| [M2b.1 implementation](docs/data/M2B1_IMPLEMENTATION.md) | Offline commands, formats, verification and status of all 14 gates |
| [Earlier MES preparation](docs/data/M2B2_ACQUISITION_PLAN.md) | Historical inactive request plan and MES gates; use the NVDA plan for new work |

## Technical direction

The runtime remains Python 3.12, NautilusTrader 1.231.0, uv 0.13.6 and pytest/Ruff/mypy. PyArrow/tzdata now directly support the implemented offline native Parquet pipeline; DuckDB and ML/LLM work remain deferred. Alpaca is selected for historical NVDA data independently of IBKR, the eventual paper/execution broker; the optional `ib` extra is installed for import verification only. Existing runtime admission still supports synthetic MES, not real NVDA. Databento/MES procurement is inactive under the new scope. No cloud infrastructure or orchestration framework is selected.

## Repository and hosting

The repository is hosted on **GitHub**. [GitHub Actions CI](.github/workflows/ci.yml) validates pushes to `main` and pull requests in one Ubuntu 24.04 / Python 3.12 job. Action dependencies are pinned to commit SHAs; the workflow grants only `contents: read` and does not persist checkout credentials. Hosting history and the existing remote are preserved; no migration or push is part of this task.

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

GitHub CI uses the official `astral-sh/setup-uv` action, installs uv 0.13.6 and Python 3.12, syncs the locked environment including the `ib` import extra, checks the lock/dependencies, and runs the existing Ruff format/lint, mypy and pytest commands above. Pytest disables sockets through project configuration and uses synthetic fixtures. Provisioning needs public dependency downloads; validation needs no API keys, market data, paid services or trading connections. No application tests or live integration modes are added. A local equivalent run does not prove the workflow has run on GitHub; verify the first hosted run after pushing.

**Legacy GitLab configuration:** `.gitlab-ci.yml` is retained for reference. Recommend removing it in a later approved cleanup if GitLab CI is no longer intended, because GitHub does not execute it and duplicate pipelines can drift. Its GitLab secret-detection template does not run on GitHub; this minimal GitHub job does not claim equivalent secret scanning. The separate smoke/demo commands remain available locally and are exercised by existing tests rather than duplicated as extra CI runs.

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

Future agent, portfolio/risk and broker modules remain absent. M2b.1 verifies Databento DBN mappings on generated fixtures only; preserve it as regression evidence. The [NVDA plan](docs/data/NVDA_DATA_PLAN.md) now governs M2b.2/M2c: rights-cleared Alpaca pilot, narrow metadata/adapter changes and NVDA-001–010 admission evidence are all pending. Historical MES gates 013/014 remain unsatisfied historical records, not required MES purchases for NVDA. M2 overall remains incomplete; no new data, implementation, account access or orders are authorized by the documentation update.

## Safety and data

Agents emit proposals; shared portfolio and risk controls alone can authorize order intents. All data, model artifacts, broker credentials and generated results stay outside Git; small deterministic synthetic fixtures remain trackable. Original Gemini reports are research inputs, not instructions or proof of profitability. Paid services, broker connectivity, paper-order activation and future live trading each require explicit authorization. Live deployment is never an automatic milestone transition.
