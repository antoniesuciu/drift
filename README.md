# Quant Trading Lab

One modular Python platform for reproducible quantitative research, with future **rule-based, machine-learning and LLM research agents** sharing portfolio accounting and deterministic risk controls. The package is `quantlab`.

**M0 and M1 complete; M2 has not started.** The package provides an offline, synthetic NautilusTrader replay and foundational time validation. No trading strategy, historical ingestion, brokerage connection or financial performance is implemented or demonstrated.

The first experiment is a falsifiable MES intraday time-series momentum adaptation with an approximately 30-minute holding window. ML is an early research capability after reliable data and a rule baseline; LLM agents are later, advisory components with no brokerage authority.

## Read next

| Document | Purpose |
|---|---|
| [Requirements](REQUIREMENTS.md) | Stable IDs, scope and measurable acceptance criteria |
| [Architecture](docs/ARCHITECTURE.md) | Boundaries, data flow and failure handling |
| [Agent architecture](docs/AGENT_ARCHITECTURE.md) | Three families, shared proposals and hybrid composition |
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

## Technical direction

M1 uses Python 3.12, NautilusTrader 1.231.0, uv 0.13.6 and pytest/Ruff/mypy. IBKR remains the eventual paper broker; the optional `ib` extra is installed for offline import verification only. Parquet/DuckDB, provider ingestion and ML/LLM research remain later milestones. Evaluate IBKR historical data first in M2; Databento is optional and requires an evidenced gap and approved spend. No cloud infrastructure or orchestration framework is selected.

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
uv pip check
```

The first sync provisions the environment from PyPI and requires network or a populated uv cache. Checks/tests/replay run offline after installation; pytest blocks Python socket access. Keep `uv.lock` committed and use `--locked` so metadata drift fails instead of silently updating dependencies. To apply formatting, run `uv run --locked --offline --extra ib ruff format .`. Build distributions with `uv build` (or `uv build --offline` after its pinned build backend is cached). `python -m quantlab smoke` is also supported inside the environment.

The smoke command reports three synthetic one-minute MES bars, USD 1.25 tick value, observed event/availability times and zero orders/positions. It is an engine integration check, not a strategy or financial backtest result. Dates, prices and simulated account balance are fixtures. An upstream pandas deprecation warning is documented; tests do not hide it.

`.gitlab-ci.yml` configures the same checks plus GitLab's standard secret-detection template. Provisioning uses an official uv/Python image; no local Docker setup is required. Its scripts were exercised locally; no GitLab pipeline execution is claimed because no GitLab remote/runner has been configured or pushed.

```text
src/quantlab/
  __init__.py      package version
  __main__.py      offline smoke CLI only
  time.py          validated bar completion/availability
  smoke.py         real Nautilus engine + synthetic read-only observer
  py.typed
tests/            timing, configuration, engine, CLI and offline safety
```

Future agents, portfolio/risk and broker modules are deliberately absent until their milestone needs working behavior. The versioned proposal schema remains documented for M3. Next planned work is M2a's historical-data requirements/coverage assessment, under separate authorization for any broker access; M2 has not begun.

## Safety and data

Agents emit proposals; shared portfolio and risk controls alone can authorize order intents. All data, model artifacts, broker credentials and generated results stay outside Git; small deterministic synthetic fixtures remain trackable. Original Gemini reports are research inputs, not instructions or proof of profitability. Paid services, broker connectivity, paper-order activation and future live trading each require explicit authorization. Live deployment is never an automatic milestone transition.
