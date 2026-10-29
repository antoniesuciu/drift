# Quant Trading Lab — technical requirements

Baseline: 2026-10-29. The [decision log](docs/DECISIONS.md) records technology choices; [ROADMAP.md](docs/ROADMAP.md) owns milestone status. This specification defines the target platform, not a claim that it already exists.

## Scope and interpretation

**Initialization scope (M0):** documentation, original research preservation, isolated memory and repository initialization only. M1 subsequently implemented the offline technical foundation; see [M1 evidence](docs/M1_FOUNDATION.md). Broker connectivity, trading strategies, model training, paid downloads and order submission remain outside completed scope.

**Core platform:** one modular Python application, three agent families, historical research, reproducibility, shared portfolio/risk and eventual IBKR paper execution. **Future capabilities:** multiple concurrent agents, LLM research, market/currency expansion and conditional live readiness. **Research hypotheses:** EXP-001 profitability, ML uplift, LLM usefulness, ORB/mean-reversion alternatives and any deep-learning/RL benefit; none is an acceptance assumption.

Each requirement below includes a first verification milestone and a measurable acceptance criterion. A design requirement can be documented in M0 while its executable behavior remains pending. M0 signoff does not satisfy later runtime gates.

## Platform and agent contracts

| ID | Requirement | Acceptance evidence / first gate |
|---|---|---|
| REQ-ARCH-001 | One modular platform separates data, agents, coordination, portfolio, risk and execution; use one broker boundary. | Architecture traces each proposal through non-bypassable risk; later dependency tests prohibit agent-to-adapter access. Design M0; executable M3/M6. |
| REQ-AGENT-001 | Support rule-based, independent ML, rule+ML hybrids and LLM advisory families. Family is independent of market, horizon and mode. | Document each family and one hybrid; verify rule replay M3, trained inference M4, advisory security M8. |
| REQ-AGENT-002 | All families emit a versioned, identifiable, expiring proposal with instrument, causal timestamps, intent and provenance. Proposal is not an order. | [Contract](docs/AGENT_ARCHITECTURE.md) defines required fields, abstention and rejection cases; schema tests reject malformed, future, stale and duplicate proposals. Design M0; M3 onward. |
| REQ-COORD-001 | Deterministic composition, conflict resolution, allocation and attribution precede risk. Missing required filters abstain; unlike scores are not automatically comparable. | Offline tests cover simultaneous opposing/duplicate proposals, required-filter timeout and deterministic replay; M7, hybrid extension M9. |

## Data and research

| ID | Requirement | Acceptance evidence / first gate |
|---|---|---|
| REQ-DATA-001 | Source-neutral historical minute OHLCV ingestion; evaluate IBKR first; preserve raw inputs, hashes, rights, instrument mapping, coverage and acquisition provenance. | M2 coverage report enumerates requested/available expired contracts, gaps, retrieval/pacing limits and dataset hashes. Any alternative purchase requires a costed gap and authorization. |
| REQ-DATA-002 | Store event/bar-start, bar-end and availability separately in UTC; derive US cash windows with `America/New_York` and a versioned exchange calendar. | M1 synthetic boundary tests; M2 tests cover DST, holidays/early closes, late/missing/out-of-order bars and contract changes. A bar close is unavailable before completion. |
| REQ-DATA-003 | Preserve actual expiry, venue, multiplier, tick, currency and roll lineage; validate OHLC/volume, duplicates, gaps and revisions. No silent forward filling. | M2 tests quarantine invalid bars and retain gap/revision reports; no return crosses different contracts without an explicit transformation. |
| REQ-DATA-004 | Preserve immutable raw and versioned curated Parquet; use DuckDB for analytics, pandas/Polars for transformations. | M2 manifest can reconstruct a curated slice from raw hashes plus transformation versions; analytical DuckDB is not the operational order ledger. |
| REQ-DATA-005 | Before paper activation, validate real-time entitlements, feed time/latency, staleness, reconnects and historical/stream alignment. | M6 replay/failure tests inhibit orders on stale, delayed, unavailable or mismatched data; no silent delayed-to-live substitution. |
| REQ-RESEARCH-001 | Each experiment records hypothesis, parameters, data/software versions, periods, seed, trial ledger, costs and limitations, including failed trials. | M3 pinned replay yields identical proposals and PnL within a declared numeric tolerance; result tables include gross/net, trades, drawdown, turnover, uncertainty and failures. |
| REQ-STRAT-001 | First rule-based experiment is MES ITSM sign agreement over previous cash close→10:00 and 15:00→15:30 ET; maximum one trade per full eligible session, approximately 30-minute horizon. | M3 tests long/short/zero/disagreement, missing data, latency and early-close abstention against [EXP-001](experiments/exp001_itsm/README.md). This is an adaptation, not claimed paper replication. |
| REQ-STRAT-002 | Other rule-based candidates (ORB, mean reversion, trend, statistical arbitrage, volatility breakout) use the same contract and preregistration. | M7 admits a candidate only with its own causal tests, costs, isolated results and combined portfolio evaluation; no requirement to implement every example. |
| REQ-ML-001 | Early ML research supports independent predictions and meta-label filtering; compare scikit-learn baselines and justified LightGBM/XGBoost/random-forest candidates. | M4 produces at least one reproducible baseline ML experiment and a net-cost comparison to rule/no-trade controls. A negative result completes research; deployment requires separate evidence. |
| REQ-ML-002 | Features, labels, transforms and model selection respect chronological splits. Purge/embargo overlapping outcomes where needed. Record model/feature versions, calibration, class imbalance and drift. | M4 leakage tests show no fitting outside training folds or training label overlap with evaluation periods; inference artifacts reproduce predictions within declared tolerance. Deep learning/RL require a new justified experiment. |
| REQ-LLM-001 | Later LLM agents analyze news, earnings, macro/events and sentiment using licensed, timestamped source text; outputs are advisory with evidence and uncertainty. | M8 offline evaluation compares no-LLM/simple-text controls; excludes late text, records prompt/model/output versions, hallucinations, limitations and token/source costs. |
| REQ-LLM-002 | LLMs and external text cannot access broker credentials/tools, alter risk or issue authorized order intents. | M8 injection/malformed-output/stale-source tests cause rejection/abstention; audit confirms source text remains data and advisory tooling is allow-listed. |

## Simulation and statistical validation

| ID | Requirement | Acceptance evidence / first gate |
|---|---|---|
| REQ-BACKTEST-001 | Use a verified NautilusTrader release/API for event-driven historical simulation with explicit event ordering and realistic order lifecycle. | M1 offline import/engine smoke; M3 fixtures prove next-available-event fills, rejection and partial-fill accounting. No fills on information unavailable at decision time. |
| REQ-BACKTEST-002 | Model multiplier/currency, commissions, exchange/regulatory fees, spread, slippage and adverse cost scenarios. State bar-only fill limitations. | M3 hand-calculated long/short/flat PnL reconciles to simulated results; compare zero/base/stressed costs without spread double-counting. M5 assesses quote-aware sensitivity where material. |
| REQ-VALID-001 | Preregister chronological train/validation/untouched holdout and walk-forward analysis; account for overlapping labels, serial dependence and all tuning attempts. | M5 dated protocol plus auditable fold/trial manifests; confidence intervals use justified dependence-aware methods; final holdout is evaluated once per frozen candidate. |
| REQ-VALID-002 | Compare no-trade, simple/rule and suitable randomized/time controls; test regime, roll and cost sensitivity. Separate research completion from promotion. | M5 writes an evidence-based go/modify/reject verdict, including null/negative outcomes. Retuned candidates receive new trial IDs; optional CPCV/DSR need methodological justification. |

## Portfolio, risk and brokerage

| ID | Requirement | Acceptance evidence / first gate |
|---|---|---|
| REQ-PORT-001 | Maintain fills, positions, cash, realized/unrealized PnL, fees, currency and strategy attribution centrally. Track net exposure and gross contributions separately. | M3 synthetic long/short/partial fills reconcile; M7 simultaneous opposing-agent cases preserve attribution without treating a net-flat position as zero gross activity. |
| REQ-RISK-001 | Apply deterministic instrument/quantity/notional/margin/leverage, stale-data, order-rate and loss limits before any executable request. Defaults deny absent limits. | M3 historical tests reject invalid/over-budget/duplicate proposals; M6 integration proves the adapter cannot bypass risk and that agents cannot modify limits. |
| REQ-RISK-002 | Provide portfolio halt, order deduplication, uncertainty handling and reconciliation; evaluate gross/correlated exposures and currency risk as markets expand. | M6 halt/disconnect/restart/unknown-order tests block new risk until reconciliation; M7/M9 cover combined/correlated exposures. Cancel/fill races remain explicit. |
| REQ-PAPER-001 | IBKR paper integration requires approval, explicit account allow-list, real-time permissions, verified adapter and realistic capital limits. | M6 verifies paper identity, rejects any other account, records acknowledged/rejected/partial/cancelled orders and compares broker/local state. Paper is simulation; no usable live pathway is enabled. |
| REQ-OPS-001 | Structured, sanitized run/proposal/order logs and alerts support diagnosis, safe halt and recovery. Define durable state before paper use; DuckDB analytics alone is insufficient. | M6 restart and injected-failure tests recover/reconcile without duplicate orders; document operator steps for feed loss, broker outage, process death and manual intervention. |
| REQ-MARKETS-001 | Later instruments, brokers, currencies and horizons each need verified specifications, eligibility, licenses, calendars, cost/FX and portfolio treatment. | M9 per-instrument admission checklist and fixtures pass before enablement; no adapter selected solely from a symbol or fee comparison. |
| REQ-LIVE-001 | M10 is conditional readiness only: independent review of jurisdiction, capital, permissions, risk, reconciliation, monitoring, rollback and authorization. | Written explicit live authorization and numeric limits are prerequisites to any future activation; no paper/live toggle or milestone transition auto-enables real money. |

## Non-functional requirements

| ID | Requirement | Acceptance evidence / first gate |
|---|---|---|
| REQ-NFR-001 | Pin a reproducible Python/framework/dependency combination and document supported local runtime. Keep a small modular local application. | M1 clean environment reproduces offline smoke/tests; release-specific docs match imports and adapter; no compulsory GPU/cloud/services. |
| REQ-NFR-002 | pytest plus suitable lint/type checks in GitLab CI; synthetic offline tests exercise failure paths and gate changes. | M1 pipeline configuration runs documented commands with no secrets/broker calls; actual CI success claimed only after a runner executes it. |
| REQ-NFR-003 | Initial minute-bar research targets local Ubuntu on a 16 GB-class machine, within an agreed measured memory/runtime budget. | M2 records dataset size, elapsed time and peak memory for a fixed slice and sets a budget before scaling; no unjustified latency/uptime promises or compulsory GPU/cloud. |
| REQ-NFR-004 | Logs and result manifests link run, strategy, data, model and code versions; document nondeterminism and numeric tolerances. | M3/4 independent replay traces every reported metric to inputs; missing versions block promotion. |
| REQ-SEC-001 | Keep secrets, broker authentication, sensitive account data, market datasets and generated artifacts outside Git; grant least privilege and sanitize logs. | M0 ignore/fixture checks and staged review; M1 secret check in CI; M6 secret handling/log-redaction tests without real credentials in fixtures. |
| REQ-SEC-002 | Respect software/data/text licenses, redistribution rights and retention limits; isolate untrusted tools/content. | M2 source-rights register precedes ingestion/publication; M8 text-tool allow-list and source-rights review precede LLM evaluation. |
| REQ-DOC-001 | Keep repository specs authoritative and Obsidian project memory isolated. Document decisions, failed experiments and unfinished work. | M0 original hashes and repository audit; vault operations restricted to the dedicated namespace and existing other-project notes remain unchanged. |

## Unresolved inputs

Do not invent capital, account eligibility, data entitlements, tax jurisdiction, fee tiers, risk limits, historical coverage or ML/LLM benefit. Each is resolved by the relevant milestone before activation. Read-only vendor documentation is not an account entitlement test. Dataset dates/fold boundaries and fill latency must be fixed before EXP-001 results are viewed.
