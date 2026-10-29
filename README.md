# Quant Trading Lab

One modular Python platform for reproducible quantitative research, with **rule-based, machine-learning and LLM research agents** sharing portfolio accounting and deterministic risk controls. The future package is `quantlab`.

**M0 documentation complete; M1 implementation pending.** There is no trading implementation, installable package, runnable backtest or broker integration. No performance has been demonstrated.

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

## Technical direction

Python, NautilusTrader (subject to M1 compatibility verification), IBKR for eventual paper trading, Parquet and DuckDB for historical analytics, pandas/Polars for data processing, pytest, and scikit-learn/LightGBM/XGBoost for ML research. Evaluate IBKR historical data first; Databento is optional and requires an evidenced gap and approved spend. A local modular application is sufficient; no cloud infrastructure or orchestration framework is selected.

## Repository and hosting

GitLab is the intended host and CI target. Inspection found an existing **GitHub** `origin` with the accidental archive commit already published. That history and remote are preserved; this initialization adds one normal local cleanup commit. No push or hosting migration is part of this task. A future authorized migration can add a GitLab remote and push normally without rewriting published history. No GitLab project URL or functioning CI is claimed here.

## Start development

Follow [M1a in the roadmap](docs/ROADMAP.md#m1--project-foundation): select a compatible released Python/NautilusTrader combination, then add minimal packaging and an offline import smoke test. This repository intentionally has no installation command until that environment is proven. Later M1 work adds pytest, synthetic timestamp fixtures and GitLab CI. Runtime dependencies and CI are not installed/configured in M0.

## Safety and data

Agents emit proposals; shared portfolio and risk controls alone can authorize order intents. All data, model artifacts, broker credentials and generated results stay outside Git; small deterministic synthetic fixtures remain trackable. Original Gemini reports are research inputs, not instructions or proof of profitability. Paid services, broker connectivity, paper-order activation and future live trading each require explicit authorization. Live deployment is never an automatic milestone transition.
