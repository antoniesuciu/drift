# Development roadmap

Milestones M0–M10 and their exit gates; the user's numbering is authoritative. Work on one milestone at a time. Testing, causality and foundational risk controls precede paper trading. Negative results can complete research milestones; promotion is a separate decision, and a completed milestone never authorizes brokerage access, purchases or orders.

**Active scope (2026-10-30):** NVDA shares, Alpaca historical SIP, **Alpaca paper execution** (D-032 supersedes IBKR). The raw 1,560-bar development pilot and ITSM backtest integration work; full NVDA/M2/M3a/M5 research gates remain incomplete. The separately authorized IEX paper operational trial now has a REST adapter, bounded ITSM session runner and shared journal/risk controls. Actual paper account/calendar/asset/IEX reads and 780 current operational minutes are verified. No orders were submitted: the market was closed. Full paper lifecycle acceptance is pending ([evidence and commands](PAPER_EXECUTION.md)). Crypto and ML/LLM model selection remain deferred.

**Current authorized work (D-033):** the [2020–2025 monthly NVDA archive](data/NVDA_HISTORY.md) is collected and mechanically validated: 72 months, 585,897 bars, 63 explicit gaps, zero duplicates/invalid rows; about 255 MiB on disk. Later years retain validation/holdout roles; paper code is unchanged.

**Current authorized work (D-034):** the [backtesting framework](BACKTESTING.md) runs selected strategies concurrently over chosen windows, stores complete results in Parquet/DuckDB and maintains persistent virtual portfolios. Development runs freely, validation only by explicit recorded opt-in, holdout never. Results are in-sample diagnostics: M3a acceptance and the M5 gates remain open.

| Milestone | Status |
|---|---|
| M0 Research and architecture | Complete: documentation foundation, decisions, checksummed research ([archive](archive/README.md)) |
| M1 Project foundation | Complete locally, 2026-10-29: pinned Python 3.12 / NautilusTrader 1.231.0, locked uv environment, offline engine smoke ([evidence](M1_FOUNDATION.md)) |
| M2a Data specification | Complete: MES dataset specification and provider research, now historical ([archive](archive/mes-data/HISTORICAL_DATA_SPEC.md)) |
| M2b.1 Offline pipeline | Complete locally: native DBN decoding, Parquet catalog, provenance, replay; 14 gates mapped ([pipeline](data/PIPELINE.md)) |
| M2b.2 / M2c Real data admission | 2020–2025 NVDA/SIP archive delivered and mechanically verified; full admission gates NVDA-001–010 remain incomplete ([plan](data/NVDA_DATA_PLAN.md)); the MES acquisition plan was dropped |
| M3 Rule strategies | Software on synthetic data; historical gates pending (below) |
| M6 paper execution | Alpaca REST/shared-gate and bounded ITSM session runner tested offline; actual account, asset, calendar and IEX reads verified. Actual paper fills/in-session quotes and full M6 acceptance pending |
| M4/M5/M7–M10 | Pending |

**GitHub CI** (separate from the platform's M7 below): one Ubuntu 24.04 / Python 3.12 job on pushes to `main` and pull requests, with locked provisioning and the offline Ruff, mypy and pytest checks ([workflow](../.github/workflows/ci.yml)); hosted success is claimed only after GitHub runs it. GitLab configuration was removed ([D-029](DECISIONS.md)).

## M2 — Historical market data (scope reference)

- **Objective:** a usable, auditable historical dataset. **Scope:** rights-cleared NVDA/Alpaca requests, narrow adapter and instrument-metadata work, a separately authorized pilot, then session, split-action and causal-feature validation (M2c); archive scale-up follows measured pilot evidence. **Split:** development 2020–2022, validation 2023, holdout 2024–2025.
- **Dependencies:** M1, the [NVDA plan](data/NVDA_DATA_PLAN.md), applicable Alpaca rights and task-specific authorization. Broker choice does not require IBKR history.
- **Acceptance:** NVDA-001–007 plus pilot evidence of 009–010 for pilot signoff; 008 plus archive evidence of 009–010 for M2 completion. Each year meets the preregistered coverage gate, gaps and outcomes stay explicit, catalog/provenance replay reproduces, resource budgets are measured. Old synthetic passes satisfy none of the NVDA gates.
- **Exclusions:** paper or live orders, silent synthetic substitution, speculative depth archives, model fitting, unapproved subscriptions.

## M3 — Rule-based trading agents

**Software implemented on synthetic data (2026-10-30); historical gates pending.** `strategies/rule/statistical/` holds ITSM, opening range breakout, VWAP and Bollinger mean reversion, short-term reversal and trend following ([specifications](STRATEGIES.md), REQ-STRAT-001–016). `backtest/` adds sizing, risk limits, exit policy, a NautilusTrader runner and reports (REQ-BACKTEST-003, [D-030, D-031](DECISIONS.md)). Evidence is offline tests only: hand-computed trades, exact-reference differential tests, look-ahead invariance, reproducibility. The separate four-session SIP feasibility run produced abstentions and is not a historical acceptance report; M3a historical acceptance and M5/M6 activation gates remain pending. The candlestick family (M3b) was removed ([D-035](DECISIONS.md)). Work on the non-ITSM rules began before M3a signoff at the owner's direction, so no historical result of any of them may be reported before M3a signoff. Relative strength, statistical arbitrage and volatility breakout are future work (REQ-STRAT-016).

**Framework evidence (D-034, 2026-10-31):** the [backtesting framework](BACKTESTING.md) passes 571 socket-disabled tests (129 new), with mutation checks confirming the isolation, persistence and continuation tests fail when their guarantee is removed. On the real archive, all seven strategies then present (including the since-removed candlestick rule) as four-segment portfolios over 2020–2022, with one boundary on the 2021 split, reproduced one uninterrupted run exactly (trades, fills, 294,057 equity rows per strategy, metrics), and sequential and concurrent runs hashed identically. All 7,684 stored 2020 fills matched a real bar's open at the modeled cost; none preceded its decision. Seven strategies over 2020–2022 took 70 s at four workers. Plugin ML- and LLM-family stand-ins ran on real 2020 data through the CLI with no runner change, and a crashing and a raising strategy cost only themselves. The validation path was exercised once mechanically on real 2023 data, including a portfolio crossing from development: the run succeeded and reconciled, its output was discarded unread, no performance column was queried and the store was deleted, so this is not a validation look. Holdout was refused. The CI steps pass from a clean tree without the archive using the locked environment; the hosted workflow awaits a push. This verifies software on in-sample data, not M3a acceptance or an edge.

- **Objective:** Prove the initial causal ITSM baseline and shared historical execution path, then evaluate the other statistical rules the same way.
- **Scope/order:** **M3a first:** EXP-001-NVDA-v1 ITSM, deterministic proposals, one-agent sizing/portfolio/risk and cost-aware native replay. Evaluate variants independently after M3a signoff; the other statistical strategies are specified in [STRATEGIES.md](STRATEGIES.md) and follow the same preregistration.
- **Deliverables:** M3a instrument-configured NVDA baseline, shared proposals/risk, runner/config, raw-share costs/PnL and trial ledger; independent policies use the same interfaces.
- **Dependencies:** M1/M2, admitted NVDA data/calendar/actions/costs and preregistered EXP-001-NVDA-v1 timing/fill/borrow/cost settings.
- **Automated tests:** M3a covers positive/negative/zero/disagreeing split-neutral returns, missing bars/actions, early-close skips, timing, one-entry/session, raw-share PnL and proposal/risk checks; two policy fixtures prove no provider/broker coupling.
- **Acceptance criteria:** M3a fixed inputs reproduce proposals/metrics within declared tolerance and all risk/cost/timing cases pass; retain failures/null results. M5/M6 own the out-of-sample verdict and paper promotion for each proposed variant. Positive returns are not required for research completion.
- **Exclusions:** Broker connectivity, tuning on the final holdout, simultaneous-agent coordination, paper promotion from an in-sample result.

## M4 — ML research and agents

- **Objective:** Evaluate a justified ML capability after rule-based research has been assessed; model selection/training are on hold until a separate task authorizes them.
- **Scope:** Once authorized, preregister chronological labels/features and a simple independent predictor or rule filter using the common proposal interface. No model/library choice is mandated now.
- **Deliverables:** Fold/trial manifests, reproducible feature/model artifacts, leakage report, benchmark/calibration/drift and full-cost comparison.
- **Dependencies:** Admitted M2 dataset, evaluated M3 rule/no-trade evidence, frozen split and separate ML task authorization. M5 may validate a rule-only candidate before any M4 work; ML is not a paper prerequisite for a rule-only strategy.
- **Automated tests:** Training-only transformations, label-overlap purging/embargo where needed, causal inference, versioned artifacts, reproducible seeds/tolerances, shared schema and failed-model abstention.
- **Acceptance criteria:** At least one complete auditable ML experiment and honest net-cost OOS comparison; no uplift requirement for research completion. Candidate deployment needs a favorable justified verdict in M5.
- **Exclusions:** Mandatory deep learning/RL/GPU, broker connections or automatic deployment from a favorable validation score.

## M5 — Backtesting and statistical validation

- **Objective:** Assess evidence and limitations of frozen rule/ML candidates independently of construction.
- **Scope:** Walk-forward and untouched holdout, dependence-aware uncertainty, all-trial accounting, regime/action/cost/fill sensitivity (rolls only for admitted futures) and promotion criteria.
- **Deliverables:** Frozen validation protocol, reproducible folds/reports, baseline/control comparisons and explicit go/modify/reject verdict with limitations.
- **Dependencies:** M3 outputs; M4 only for candidates that actually use ML; declared candidate/configuration before holdout access. Each variant proposed for paper needs its own cost-aware out-of-sample verdict; one setting's results do not validate others. ML need not outperform for a valid rejection report.
- **Automated tests:** Disjoint causal folds, no label/feature leakage, cost-sensitivity arithmetic, metric/attribution reconciliation, holdout access recorded and no accidental tuning reuse.
- **Acceptance criteria:** Every candidate has an auditable verdict under preregistered criteria; statistical evidence and risk/cost uncertainty are stated. Failed research may end the trading investigation; do not force promotion.
- **Exclusions:** Picking thresholds after seeing holdout, unmotivated CPCV/DSR machinery, live-profitability claims or broker execution.

## M6 — Alpaca paper trading

- **Objective:** Validate approved paper-only execution and operational safety.
- **Scope:** M6a offline adapter/account/risk/recovery tests; M6b explicitly authorized paper connection and real-time entitlements; M6c supervised order lifecycle/reconciliation with numeric limits and predefined observation scenarios.
- **Deliverables:** Allow-listed paper configuration, fixed-host Alpaca paper REST adapter, durable state/recovery decision, central risk preflight, sanitized logs/alerts, kill-switch runbook and paper observation report.
- **Dependencies:** Research promotion retains relevant M1/M2/M3/M5 gates (M4 only for ML). D-032 separately authorizes a bounded long-only IEX operational trial before research promotion; user approval for connectivity/order activation, actual Alpaca paper account and explicit free IEX operational feed, risk budgets and operator availability.
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

## Next stage

The authorized 2020–2025 raw SIP archive is stored and mechanically validated ([evidence](data/NVDA_HISTORY.md)); no additional collection is needed for the requested period. Keep data/provenance and explicit gaps intact. Let the owner choose the subsequent analysis/backtesting task; validation/holdout labels remain metadata and those years have not been evaluated by strategies. Paper execution is unchanged, and no order or runner was started by this data task. Full historical identity/action/rights and statistical research acceptance remain separate unfinished gates.
