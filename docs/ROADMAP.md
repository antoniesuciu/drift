# Development roadmap

Milestones M0–M10 and their exit gates; the user's numbering is authoritative. Work on one milestone at a time. Testing, causality and foundational risk controls precede paper trading. Negative results can complete research milestones; promotion is a separate decision, and a completed milestone never authorizes brokerage access, purchases or orders.

**Active scope (2026-10-30):** NVDA shares, Alpaca historical SIP, IBKR as the eventual broker. The ingestion pipeline still accepts only synthetic MES; the M3 strategies and the backtest runner exist as software on synthetic data. All real NVDA gates, M2c and M2 overall are pending. Crypto and ML/LLM model selection are deferred.

| Milestone | Status |
|---|---|
| M0 Research and architecture | Complete: documentation foundation, decisions, checksummed research ([archive](archive/README.md)) |
| M1 Project foundation | Complete locally, 2026-10-29: pinned Python 3.12 / NautilusTrader 1.231.0, locked uv environment, offline engine smoke ([evidence](M1_FOUNDATION.md)) |
| M2a Data specification | Complete: MES dataset specification and provider research, now historical ([archive](archive/mes-data/HISTORICAL_DATA_SPEC.md)) |
| M2b.1 Offline pipeline | Complete locally: native DBN decoding, Parquet catalog, provenance, replay; 14 gates mapped ([pipeline](data/PIPELINE.md)) |
| M2b.2 / M2c Real data admission | Pending, replanned for NVDA/Alpaca: gates NVDA-001–010 ([plan](data/NVDA_DATA_PLAN.md)); the MES acquisition plan was dropped |
| M3 Rule strategies | Software on synthetic data; historical gates pending (below) |
| M4–M10 | Pending |

**GitHub CI** (separate from the platform's M7 below): one Ubuntu 24.04 / Python 3.12 job on pushes to `main` and pull requests, with locked provisioning and the offline Ruff, mypy and pytest checks ([workflow](../.github/workflows/ci.yml)); hosted success is claimed only after GitHub runs it. GitLab configuration was removed ([D-029](DECISIONS.md)).

## M2 — Historical market data (scope reference)

- **Objective:** a usable, auditable historical dataset. **Scope:** rights-cleared NVDA/Alpaca requests, narrow adapter and instrument-metadata work, a separately authorized pilot, then session, split-action and causal-feature validation (M2c); archive scale-up follows measured pilot evidence. **Split:** development 2020–2022, validation 2023, holdout 2024–2025.
- **Dependencies:** M1, the [NVDA plan](data/NVDA_DATA_PLAN.md), applicable Alpaca rights and task-specific authorization. Broker choice does not require IBKR history.
- **Acceptance:** NVDA-001–007 plus pilot evidence of 009–010 for pilot signoff; 008 plus archive evidence of 009–010 for M2 completion. Each year meets the preregistered coverage gate, gaps and outcomes stay explicit, catalog/provenance replay reproduces, resource budgets are measured. Old synthetic passes satisfy none of the NVDA gates.
- **Exclusions:** paper or live orders, silent synthetic substitution, speculative depth archives, model fitting, unapproved subscriptions.

## M3 — Rule-based trading agents

**Software implemented on synthetic data (2026-10-30); historical gates pending.** `strategies/rule/statistical/` holds ITSM, opening range breakout, VWAP and Bollinger mean reversion, short-term reversal and trend following; `strategies/rule/candlestick/` holds the ten-pattern detector, 1m–1h aggregation, four filters and the policy ([specifications](STRATEGIES.md), REQ-STRAT-001–016). `backtest/` adds sizing, risk limits, exit policy, a NautilusTrader runner and reports (REQ-BACKTEST-003, [D-030, D-031](DECISIONS.md)). Evidence is offline tests only: hand-computed trades, exact-reference differential tests, look-ahead invariance, reproducibility. There is no real data and no measured return; M3a historical acceptance, CANDLE-008 and every M5/M6 gate remain pending. Work on the non-ITSM rules began before M3a signoff at the owner's direction, so no historical result of any of them may be reported before M3a signoff. Relative strength, statistical arbitrage and volatility breakout are future work (REQ-STRAT-016).

- **Objective:** Prove the initial causal ITSM baseline and shared historical execution path, then add a testable candlestick rule capability.
- **Scope/order:** **M3a first:** EXP-001-NVDA-v1 ITSM, deterministic proposals, one-agent sizing/portfolio/risk and cost-aware native replay. **M3b only after M3a signoff (as evidence):** [candlestick pattern agents](STRATEGIES.md) under RULE, with all 10 detection forms, configurable instruments and 1m/5m/15m/30m/1h candles, optional confirmations and entry/exit/stop/target rules. Evaluate variants independently; the other statistical strategies are specified in [STRATEGIES.md](STRATEGIES.md) and follow the same preregistration.
- **Deliverables:** M3a instrument-configured NVDA baseline, shared proposals/risk, runner/config, raw-share costs/PnL and trial ledger; independent policies use the same interfaces. M3b reusable completed-candle detectors/shape records, rule-policy/shared-proposal integration, causal feature-consumption contract and at least one preregistered candlestick historical report with full costs and all attempted variants recorded.
- **Dependencies:** M1/M2, admitted NVDA data/calendar/actions/costs and preregistered EXP-001-NVDA-v1 timing/fill/borrow/cost settings. M3b requires recorded M3a completion.
- **Automated tests:** M3a covers positive/negative/zero/disagreeing split-neutral returns, missing bars/actions, early-close skips, timing, one-entry/session, raw-share PnL and proposal/risk checks; two policy fixtures prove no provider/broker coupling. M3b adds the CANDLE-001–008/010 detector-side cases: all patterns/timeframes, hand-calculated aggregation, instrument isolation, confirmation warmup/conflicts, future-data invariance, shared proposal identity and entry/exit/protection/cost edge cases.
- **Acceptance criteria:** M3a fixed inputs reproduce proposals/metrics within declared tolerance and all risk/cost/timing cases pass before M3b. M3b passes CANDLE-001–008 and reusable detector-side CANDLE-010 evidence; retain failures/null results. M4 tests fitted ML reuse; M5/M6 own CANDLE-009 out-of-sample verdict and paper promotion for each proposed variant. Positive returns are not required for research completion.
- **Exclusions:** Broker connectivity, tuning on the final holdout, simultaneous-agent coordination, paper promotion from an in-sample result.

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

The next separate task implements only the narrow offline NVDA adapter and metadata prerequisites and the fixture gates in [NVDA_DATA_PLAN.md](data/NVDA_DATA_PLAN.md), then seeks rights- and access-cleared pilot acquisition authorization. Preserve the synthetic MES regressions, the native catalog and causal snapshots. Full archive acquisition, historical rule results, broker connectivity and orders are subsequent gates.
