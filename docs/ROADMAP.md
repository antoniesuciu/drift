# Development roadmap

**M0, M1, M2a and M2b.1 retain their completed historical evidence. Active scope is now NVDA / Alpaca historical SIP / IBKR (2026-10-30).** The runtime remains synthetic MES-only. M2b.2 is replanned around the [NVDA admission plan](data/NVDA_DATA_PLAN.md); all real NVDA gates, M2c and M2 overall remain incomplete. M3–M10 remain pending; crypto and ML/LLM selection are deferred. Milestone completion does not authorize brokerage access, purchases or orders. Work on one milestone/task at a time.

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

**Current direction:** admit NVDA Alpaca data through the existing native catalog/replay path; retain development 2020–2022, validation 2023, holdout 2024–2025. Earlier MES specifications and requests below are historical evidence, not active acquisition instructions. NVDA-001–010 govern new admission; historical MES 013/014 are not relabeled as NVDA passes or required purchases.

**M2a complete, 2026-10-29 — research/specification only.** [Dataset specification](data/HISTORICAL_DATA_SPEC.md), [provider comparison](data/PROVIDER_COMPARISON.md) and [M2b design/gates](data/INGESTION_DESIGN.md) define the 2020–2025 archive, development-only 2022 pilot, timestamp/calendar/roll rules, conditional Databento recommendation and unresolved cost/retention/coverage gates. No market data, dependencies, ingestion code or broker connections were introduced by M2a. At that signoff, M2b/M2c and real-data admission were unstarted.

**M2b.1 complete locally, 2026-10-29 — synthetic offline implementation.** [Evidence and all 14 gate statuses](data/M2B1_IMPLEMENTATION.md): native DBN decoding, validated metadata/time/calendar/roll, exact Parquet/provenance round-trip and deterministic order-free replay. **120 tests pass**, including unchanged M1 tests; format/lint/types/lock/dependency checks pass. Offline portions of 001–012 are verified; real-service/calendar/metadata evidence and 013/014 remain pending. No acquisition or broker connection. M2b.2, M2c and full M2 remain incomplete.

**M2b.2 preparation recorded, 2026-10-29 — research and planning only.** [Acquisition/acceptance plan](data/M2B2_ACQUISITION_PLAN.md), linked primary-source vendor/market research and a machine-readable nine-job pilot schedule. Exact pilot/archive/FirstRate purchase totals and applicable Databento retention rights remain unresolved; public prices are comparison inputs only. Historical roll changes, dated-calendar gaps, real-definition compatibility and monthly-batch prerequisites are explicit. The unchanged 120-test offline suite passes. No account query, market-data download, purchase or admission occurred; gates 013/014, M2c and M2 overall remain pending.

- **Objective:** Create a usable, auditable historical/feature dataset.
- **Scope:** M2a historical MES planning is retained; active M2b.2 defines rights-cleared NVDA/Alpaca requests, narrow adapter/instrument-metadata work and separately authorized pilot admission. M2c validates sessions, split actions and causal feature views; archive scale-up follows measured pilot evidence.
- **Deliverables:** Coverage/rights report, provider-neutral ingestion, immutable raw and partitioned Parquet, provenance manifests, optional DuckDB queries and dataset-quality report.
- **Dependencies:** M1; [NVDA plan](data/NVDA_DATA_PLAN.md), applicable Alpaca rights/access and task-specific authorization before implementation/acquisition. Broker selection does not require IBKR history. No paid alternative or account connection is implied.
- **Automated tests:** Preserve MES regressions; add NVDA source pagination/feed identity, metadata-driven units, raw/adjusted actions, duplicates/gaps/revisions, availability, holidays/early closes/DST, native manifest reconstruction and future invariance. Equivalent source fixtures and a second synthetic instrument prove shared interfaces without another real market.
- **Acceptance criteria:** NVDA-001–007 plus pilot 009–010 evidence for pilot signoff; 008 plus archive 009–010 evidence for M2 completion. Each year meets the preregistered coverage gate, gaps/outcomes remain explicit, catalog/provenance replay is reproducible and resource budgets measured. All NVDA gates are pending; old synthetic passes do not satisfy them.
- **Exclusions:** Paper/live orders, silent synthetic substitution, speculative depth archives, model fitting or unapproved subscriptions.

## M3 — Rule-based trading agents

- **Objective:** Prove the initial causal ITSM baseline and shared historical execution path, then add a testable candlestick rule capability.
- **Scope/order:** **M3a first:** EXP-001-NVDA-v1 ITSM, deterministic proposals, one-agent sizing/portfolio/risk and cost-aware native replay. **M3b only after M3a signoff:** [Candlestick Pattern Agents](CANDLESTICK_AGENTS.md) under RULE, with all 10 detection forms, configurable instruments and 1m/5m/15m/30m/1h candles, optional confirmations and entry/exit/stop/target rules. Evaluate variants independently; other statistical strategies remain candidates.
- **Deliverables:** M3a instrument-configured NVDA baseline, shared proposals/risk, runner/config, raw-share costs/PnL and trial ledger; independent policies use the same interfaces. M3b reusable completed-candle detectors/shape records, rule-policy/shared-proposal integration, causal feature-consumption contract and at least one preregistered candlestick historical report with full costs and all attempted variants recorded.
- **Dependencies:** M1/M2, admitted NVDA data/calendar/actions/costs and preregistered EXP-001-NVDA-v1 timing/fill/borrow/cost settings. M3b requires recorded M3a completion; this requirements update neither starts M3 nor enlarges current M2 implementation.
- **Automated tests:** M3a covers positive/negative/zero/disagreeing split-neutral returns, missing bars/actions, early-close skips, timing, one-entry/session, raw-share PnL and proposal/risk checks; two policy fixtures prove no provider/broker coupling. M3b adds the CANDLE-001–008/010 detector-side cases: all patterns/timeframes, hand-calculated aggregation, instrument isolation, confirmation warmup/conflicts, future-data invariance, shared proposal identity and entry/exit/protection/cost edge cases.
- **Acceptance criteria:** M3a fixed inputs reproduce proposals/metrics within declared tolerance and all risk/cost/timing cases pass before M3b. M3b passes CANDLE-001–008 and reusable detector-side CANDLE-010 evidence; retain failures/null results. M4 tests fitted ML reuse; M5/M6 own CANDLE-009 out-of-sample verdict and paper promotion for each proposed variant. Positive returns are not required for research completion.
- **Exclusions:** Broker connectivity, tuning on final holdout, starting candlestick implementation before the ITSM baseline, implementing every other rule family, simultaneous-agent coordination or paper promotion from an in-sample result.

## M4 — ML research and agents

- **Objective:** Evaluate a justified ML capability after rule-based research has been assessed; model selection/training are on hold until a separate task authorizes them.
- **Scope:** Once authorized, preregister chronological labels/features and a simple independent predictor or rule filter using the common proposal interface. No model/library choice is mandated now. Candlestick observations may be reused through the same versioned detector/cutoff contract; they are inputs to evaluate, not assumed predictive features.
- **Deliverables:** Fold/trial manifests, reproducible feature/model artifacts, leakage report, benchmark/calibration/drift and full-cost comparison.
- **Dependencies:** Admitted M2 dataset, evaluated M3 rule/no-trade evidence, frozen split and separate ML task authorization. M5 may validate a rule-only candidate before any M4 work; ML is not a paper prerequisite for a rule-only strategy.
- **Automated tests:** Training-only transformations, label-overlap purging/embargo where needed, causal inference, versioned artifacts, reproducible seeds/tolerances, shared schema and failed-model abstention.
- **Acceptance criteria:** At least one complete auditable ML experiment and honest net-cost OOS comparison; no uplift requirement for research completion. Candidate deployment needs a favorable justified verdict in M5.
- **Exclusions:** Mandatory deep learning/RL/GPU, broker connections or automatic deployment from a favorable validation score.

## M5 — Backtesting and statistical validation

- **Objective:** Assess evidence and limitations of frozen rule/ML candidates independently of construction.
- **Scope:** Walk-forward and untouched holdout, dependence-aware uncertainty, all-trial accounting, regime/action/cost/fill sensitivity (rolls only for admitted futures) and promotion criteria.
- **Deliverables:** Frozen validation protocol, reproducible folds/reports, baseline/control comparisons and explicit go/modify/reject verdict with limitations.
- **Dependencies:** M3 outputs; M4 only for candidates that actually use ML; declared candidate/configuration before holdout access. Each candlestick variant proposed for paper needs its own cost-aware out-of-sample verdict; one pattern's results do not validate other settings. ML need not outperform for a valid rejection report.
- **Automated tests:** Disjoint causal folds, no label/feature leakage, cost-sensitivity arithmetic, metric/attribution reconciliation, holdout access recorded and no accidental tuning reuse.
- **Acceptance criteria:** Every candidate has an auditable verdict under preregistered criteria; statistical evidence and risk/cost uncertainty are stated. Failed research may end the trading investigation; do not force promotion.
- **Exclusions:** Picking thresholds after seeing holdout, unmotivated CPCV/DSR machinery, live-profitability claims or broker execution.

## M6 — Interactive Brokers paper trading

- **Objective:** Validate approved paper-only execution and operational safety.
- **Scope:** M6a offline adapter/account/risk/recovery tests; M6b explicitly authorized paper connection and real-time entitlements; M6c supervised order lifecycle/reconciliation with numeric limits and predefined observation scenarios.
- **Deliverables:** Allow-listed paper configuration, verified IBKR adapter, durable state/recovery decision, central risk preflight, sanitized logs/alerts, kill-switch runbook and paper observation report.
- **Dependencies:** Relevant M1/M2/M3/M5 gates (M4 only if the candidate uses ML), an explicitly reviewed NVDA candidate, user approval for connectivity/order activation, actual IBKR stock permissions/real-time feed, risk budgets and operator availability.
- **Automated tests:** Wrong/live account rejection, denied/duplicate/stale/over-limit orders, pending exposure, partial/rejected fills, timeout/reconnect, unknown submission, process restart, cancel/fill race, reconcile-before-resume and halt.
- **Acceptance criteria:** Offline negative paths pass before connection; authorized supervised scenarios reconcile all orders/positions/cash/fees without unexplained residuals; failures halt new risk. Paper fills are reported as simulations, never exchange-fill proof.
- **Exclusions:** Live-capital functionality, unattended promotion or performance claims from nominal simulator capital.

## M7 — Multiple trading agents

- **Objective:** Evaluate concurrent rule and ML strategies with reliable attribution.
- **Scope:** Independently evaluated agents/horizons/instruments in combined historical simulation first; add one candidate at a time, then approved paper concurrency only after M6 controls.
- **Deliverables:** Multi-agent configs, deterministic conflict/netting policy, gross/net exposure and PnL attribution, allocation and isolated-versus-joint comparisons.
- **Dependencies:** Relevant M3/M5/M6 evidence, plus M4 only for ML strategies; each added strategy needs its own data/specification, validation verdict and permissions.
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

## Next stage — authorized task required

Specifications now align with the confirmed NVDA/Alpaca/IBKR scope and modular interfaces. The next separate task should implement only the narrow offline NVDA adapter/metadata prerequisites and fixture gates in [NVDA_DATA_PLAN.md](data/NVDA_DATA_PLAN.md), then seek rights/access-cleared pilot acquisition authorization. Preserve synthetic MES regressions, the native catalog and causal snapshots. Full archive, rule implementation, broker connectivity and orders remain subsequent gates; the old nine-job MES schedule is inactive. The user authorized a local documentation commit after review; implementation, dependency changes, acquisition and push remain outside this scope.
