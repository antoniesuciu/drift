# Development roadmap

**M0, M1, M2a and M2b.1 are complete. Next task: M2b.2 — pending, not started.** M2 overall remains incomplete; M2c and M3–M10 remain pending. Milestone completion does not authorize brokerage access, purchases or orders. Work on one milestone/task at a time.

The user's final M0–M10 numbering is authoritative over older archived drafts. Testing, causality and foundational risk controls precede paper trading. Negative results can complete research milestones; promotion is a separate decision.

## M0 — Research and architecture

- **Objective:** Establish an implementation-ready documentation foundation.
- **Scope:** Reconcile handoff, all three reports, requirements, decisions, roadmap, agent workflow and isolated memory; safe Git cleanup.
- **Deliverables:** [README](../README.md), [requirements](../REQUIREMENTS.md), [architecture](ARCHITECTURE.md), [agent contract](AGENT_ARCHITECTURE.md), [decisions](DECISIONS.md), this roadmap, [synthesis](RESEARCH_SYNTHESIS.md), [providers](COSTS_AND_PROVIDERS.md), originals, [EXP-001](../experiments/exp001_itsm/README.md), ignore rules and memory notes.
- **Dependencies:** Supplied archive/task; read-only Git/remote and vault inspection; primary-source verification.
- **Automated tests:** Documentation links/anchors, requirement-ID uniqueness, complete milestone fields, original hashes, ignore/fixture policy and staged-file checks; no trading tests exist yet.
- **Acceptance criteria:** All required docs reviewed and consistent; three original hashes match; temporary handoff/duplicate files removed after reconciliation; other-project memory unchanged; one local commit with published history preserved. See [initialization audit](INITIALIZATION.md).
- **Exclusions:** Runtime code/CI scaffold, installations, broker connections, datasets, model training, orders, push or hosting migration.

## M1 — Project foundation

**Complete locally, 2026-10-29.** [M1 evidence](M1_FOUNDATION.md) records the verified tuple, 36 passing offline tests, formatting/lint/types, fresh installation, deterministic engine smoke and CI configuration. No server-side GitLab pipeline has run; the acceptance gate explicitly distinguishes configured CI from executed CI.

- **Objective:** Prove the minimum offline Python/framework environment.
- **Scope:** M1a compatible released Python/NautilusTrader/API/docs selection and minimal package/import smoke; M1b tiny synthetic engine/time fixtures; M1c pytest, lint/types as justified and GitLab CI configuration.
- **Deliverables:** `pyproject.toml`, dependency lock, minimal `src/quantlab/`, tests and documented local/CI commands; compatibility record including adapter limitations. No empty agent modules.
- **Dependencies:** M0 acceptance; current official release-specific docs. See [compatibility gate](COSTS_AND_PROVIDERS.md).
- **Automated tests:** Import and event-driven engine smoke offline; UTC/ET DST and bar completion/availability cases; lint/type checks for introduced code, reproducible clean install.
- **Acceptance criteria:** Pinned tuple passes offline on supported local runtime; CI config uses no credentials/network orders. Record actual CI run separately once GitLab runner exists; config alone is not a green pipeline.
- **Exclusions:** Broker calls, paid data, strategies, ML/LLM runtime, orchestration or account configuration.

## M2 — Historical market data

**M2a complete, 2026-10-29 — research/specification only.** [Dataset specification](data/HISTORICAL_DATA_SPEC.md), [provider comparison](data/PROVIDER_COMPARISON.md) and [M2b design/gates](data/INGESTION_DESIGN.md) define the 2020–2025 archive, development-only 2022 pilot, timestamp/calendar/roll rules, conditional Databento recommendation and unresolved cost/retention/coverage gates. No market data, dependencies, ingestion code or broker connections were introduced by M2a. At that signoff, M2b/M2c and real-data admission were unstarted.

**M2b.1 complete locally, 2026-10-29 — synthetic offline implementation.** [Evidence and all 14 gate statuses](data/M2B1_IMPLEMENTATION.md): native DBN decoding, validated metadata/time/calendar/roll, exact Parquet/provenance round-trip and deterministic order-free replay. **120 tests pass**, including unchanged M1 tests; format/lint/types/lock/dependency checks pass. Offline portions of 001–012 are verified; real-service/calendar/metadata evidence and 013/014 remain pending. No acquisition or broker connection. M2b.2, M2c and full M2 remain incomplete.

- **Objective:** Create a usable, auditable historical/feature dataset.
- **Scope:** M2a exact MES history requirements and IBKR coverage feasibility; M2b authorized acquisition and raw/curated storage; M2c validation, contract rolls and causal feature views. Split work by these tasks.
- **Deliverables:** Coverage/rights report, provider-neutral ingestion, immutable raw and partitioned Parquet, provenance manifests, optional DuckDB queries and dataset-quality report.
- **Dependencies:** M1; explicit authorization before any broker connectivity; approved cost/rights decision before paid alternatives. IBKR insufficiency is documented, not silently worked around.
- **Automated tests:** Duplicates/gaps/out-of-order/invalid OHLCV, timestamp availability, holidays/early closes/DST, expiry mapping and roll discontinuities, reproducible manifest reconstruction.
- **Acceptance criteria:** Required period/contracts/folds defined; available coverage quantified; gaps quarantined; dataset reconstructible by hashes; resource use measured and budget agreed. Any unresolved historical gap blocks the affected real-data experiment, not the integrity tests.
- **Exclusions:** Paper/live orders, silent synthetic substitution, speculative depth archives, model fitting or unapproved subscriptions.

## M3 — Rule-based trading agents

- **Objective:** Prove the first causal rule-based strategy and minimal shared historical execution path.
- **Scope:** EXP-001 MES ITSM, deterministic proposals, single-agent sizing/portfolio/risk, cost-aware event-driven baseline replay. Other statistical strategies remain candidates.
- **Deliverables:** Baseline rule agent, experiment runner/config, historical portfolio/risk checks, timing/cost/PnL report and trial ledger.
- **Dependencies:** M1/M2, verified contract specifications and preregistered EXP-001 timing/fill/cost settings.
- **Automated tests:** Positive/negative/zero/disagreeing returns; missing bars, roll/early-close skips, late decision/no future fills, one entry per session; long/short/partial-fill PnL; stale/duplicate/oversized proposals rejected.
- **Acceptance criteria:** Fixed inputs reproduce proposals/metrics within declared tolerance; all risk/cost/timing cases pass; failures and null results retained. Positive returns are not required.
- **Exclusions:** Broker connectivity, tuning on final holdout, implementing every rule family, production multi-agent coordination.

## M4 — ML research and agents

- **Objective:** Evaluate ML as an early independent or hybrid research capability.
- **Scope:** Chronological labels/features, simple scikit-learn baseline; justified LightGBM/XGBoost/random-forest comparison; one independent predictor or rule+ML filter with shared proposal semantics.
- **Deliverables:** Fold/trial manifests, reproducible feature/model artifacts, leakage report, benchmark/calibration/drift and full-cost comparison.
- **Dependencies:** M2 dataset, M3 rule/no-trade controls and frozen split protocol before fitting. Initial validation belongs here; M5 independently assesses promotion.
- **Automated tests:** Training-only transformations, label-overlap purging/embargo where needed, causal inference, versioned artifacts, reproducible seeds/tolerances, shared schema and failed-model abstention.
- **Acceptance criteria:** At least one complete auditable ML experiment and honest net-cost OOS comparison; no uplift requirement for research completion. Candidate deployment needs a favorable justified verdict in M5.
- **Exclusions:** Mandatory deep learning/RL/GPU, broker connections or automatic deployment from a favorable validation score.

## M5 — Backtesting and statistical validation

- **Objective:** Assess evidence and limitations of frozen rule/ML candidates independently of construction.
- **Scope:** Walk-forward and untouched holdout, dependence-aware uncertainty, all-trial accounting, regime/roll/cost/fill sensitivity and promotion criteria.
- **Deliverables:** Frozen validation protocol, reproducible folds/reports, baseline/control comparisons and explicit go/modify/reject verdict with limitations.
- **Dependencies:** M3/M4 outputs and a declared candidate/configuration before holdout access. ML need not outperform for a valid rejection report.
- **Automated tests:** Disjoint causal folds, no label/feature leakage, cost-sensitivity arithmetic, metric/attribution reconciliation, holdout access recorded and no accidental tuning reuse.
- **Acceptance criteria:** Every candidate has an auditable verdict under preregistered criteria; statistical evidence and risk/cost uncertainty are stated. Failed research may end the trading investigation; do not force promotion.
- **Exclusions:** Picking thresholds after seeing holdout, unmotivated CPCV/DSR machinery, live-profitability claims or broker execution.

## M6 — Interactive Brokers paper trading

- **Objective:** Validate approved paper-only execution and operational safety.
- **Scope:** M6a offline adapter/account/risk/recovery tests; M6b explicitly authorized paper connection and real-time entitlements; M6c supervised order lifecycle/reconciliation with numeric limits and predefined observation scenarios.
- **Deliverables:** Allow-listed paper configuration, verified IBKR adapter, durable state/recovery decision, central risk preflight, sanitized logs/alerts, kill-switch runbook and paper observation report.
- **Dependencies:** M1–M5 gates, an explicitly reviewed candidate, user approval for connectivity/order activation, actual account permissions/real-time feed, risk budgets and operator availability.
- **Automated tests:** Wrong/live account rejection, denied/duplicate/stale/over-limit orders, pending exposure, partial/rejected fills, timeout/reconnect, unknown submission, process restart, cancel/fill race, reconcile-before-resume and halt.
- **Acceptance criteria:** Offline negative paths pass before connection; authorized supervised scenarios reconcile all orders/positions/cash/fees without unexplained residuals; failures halt new risk. Paper fills are reported as simulations, never exchange-fill proof.
- **Exclusions:** Live-capital functionality, unattended promotion or performance claims from nominal simulator capital.

## M7 — Multiple trading agents

- **Objective:** Evaluate concurrent rule and ML strategies with reliable attribution.
- **Scope:** Independently evaluated agents/horizons/instruments in combined historical simulation first; add one candidate at a time, then approved paper concurrency only after M6 controls.
- **Deliverables:** Multi-agent configs, deterministic conflict/netting policy, gross/net exposure and PnL attribution, allocation and isolated-versus-joint comparisons.
- **Dependencies:** M3–M6; each added strategy needs its own data/specification, validation verdict and permissions.
- **Automated tests:** Opposing and duplicate proposals, simultaneous pending orders, allocation FLAT semantics, gross/net attribution, correlated risk, deterministic scheduling and portfolio halt across agents.
- **Acceptance criteria:** Joint ledger reconciles to fills, agent contributions and net holdings; combined exposure never bypasses limits; any paper concurrency separately authorized.
- **Exclusions:** Distributed agents, unlimited strategies, LLM tool infrastructure or unreviewed market expansion.

## M8 — LLM research agents

- **Objective:** Evaluate structured language-based financial research safely.
- **Scope:** One justified news/earnings/macro/event use case with licensed timestamped text, advisory schema, evidence evaluation, model/prompt versions and cost ceilings.
- **Deliverables:** As-of text/evaluation set, advisory agent, captured-output replay, provenance/error/cost report and no-LLM/simple-text baseline.
- **Dependencies:** Shared contracts; M2-like textual data/rights checks, M7 shared attribution; approval for any paid models/text/tools. Disclose historical model-knowledge contamination.
- **Automated tests:** Injection, fabricated citations, future/revised text, malformed/expired output, tool denial, unavailable model, budget exhaustion and inability to mutate risk or reach broker execution.
- **Acceptance criteria:** Evaluated evidence quality, limitations and full costs; missing/invalid required advice abstains; no direct brokerage authority. Research can conclude LLM value is absent.
- **Exclusions:** LLM order placement, arbitrary tools, selected vendor by default or mandatory inference spend.

## M9 — Coordination and market expansion

- **Objective:** Validate justified hybrid/portfolio coordination and separately admit new markets/currencies.
- **Scope:** M9a registered rule→ML→LLM advisory composition in historical evaluation; M9b reviewed portfolio allocation/risk; M9c one independently verified instrument/venue/currency extension at a time. No single large rollout.
- **Deliverables:** Composition lineage and fallback policy, portfolio comparison, per-market eligibility/data/cost/calendar/FX checklist and admission record; paper coordination only when explicitly approved.
- **Dependencies:** M5–M8 evidence, configured numeric risk and actual eligibility/feed rights; new instrument/strategy evaluation and no-LLM controls.
- **Automated tests:** Required-filter loss, conflicting signals, delayed data/advice, net and correlated exposure, FX valuation and missing FX quotes, session/roll/corporate-action cases and safe multi-agent restart.
- **Acceptance criteria:** Every added policy/market passes isolated and combined tests, reconciles portfolio state and preserves risk invariants; unsupported currencies/venues are rejected.
- **Exclusions:** Unbounded expansion, opaque score averaging, new broker selection solely from fees or live execution.

## M10 — Conditional live-trading readiness

- **Objective:** Decide whether a separate live capability should ever be authorized.
- **Scope:** Independent review of capital, jurisdiction/tax/permissions, fees, limits, operational recovery, monitoring and an explicitly bounded rollout/rollback proposal.
- **Deliverables:** Evidence dossier, operator/runbook review, rejected/open risks and written go/no-go decision. Rejection or indefinite deferral is valid.
- **Dependencies:** Relevant earlier gates, sustained documented paper failure/recovery observations, actual legal/account review and explicit human decision; no residence inferred from workstation timezone.
- **Automated tests:** Repeat risk/account/credential isolation and fault-recovery cases against reviewed release; prove missing authorization blocks activation. No real-money test orders as part of this roadmap gate.
- **Acceptance criteria:** Every readiness item has evidence and owner; no unresolved critical safety issue; any future live implementation/activation receives separate explicit authorization and numeric limits.
- **Exclusions:** Automatic live enablement, implied profit guarantees or authorization created merely by passing tests.

## Next implementation task (not started)

M2b.2 first resolves approved exact pricing, retention/rights, bounded acquisition and authoritative calendars/contract metadata; then narrowly enables real-data admission and validates the two 2022 pilot slices. Existing offline tests and immutable storage remain mandatory. Gate 013 requires actual pilot evidence; 014 requires authorized archive/coverage/resource evidence. Do not begin M2b.2 automatically.
