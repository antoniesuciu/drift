# Platform architecture

**Active scope, 2026-10-30:** NVDA shares, Alpaca historical SIP, IBKR eventual execution. The existing runtime remains synthetic MES-only. [NVDA data/admission](data/NVDA_DATA_PLAN.md) is current; older MES metadata examples describe preserved implementation, not the next real market. Crypto is deferred; ML/LLM model selection waits for rule evaluation.

Design baseline: 2026-10-29; scope/interface revision: 2026-10-30. Existing M1/M2b.1 code is offline synthetic evidence; the new NVDA design remains pending. [Requirements](../REQUIREMENTS.md) own acceptance criteria; [decisions](DECISIONS.md) own technology status; [glossary](../GLOSSARY.md) owns terminology.

## Shape and boundaries

A local modular Python application is sufficient. Use library interfaces and one event loop/process first; no message broker, microservices, LLM orchestration framework or operational database is selected now. Create `src/quantlab/` modules only when an implementation milestone needs them.

```mermaid
flowchart TD
    Historical[Alpaca NVDA history - admission pending] --> Data[Validation, normalization and causal features]
    Streaming[Approved streaming sources - M6] --> Data
    Text[Point-in-time text - M8] --> LLM[LLM advisory agents]
    Data --> Rules[Rule-based agents]
    Data --> ML[ML agents and filters]
    Data --> Patterns[Reusable candlestick detection - M3b]
    Patterns --> Rules
    Patterns --> ML
    Rules --> Proposals[Versioned proposals]
    ML --> Proposals
    LLM --> Proposals
    Proposals --> Policy[Validity, deterministic composition and allocation]
    Policy --> Risk[Central deterministic risk gate]
    Ledger[Shared portfolio and reconciled state] --> Risk
    Risk --> Execution[Authorized order intents and execution preflight]
    Execution --> Simulation[NautilusTrader historical simulator]
    Execution --> Paper[IBKR paper adapter - M6 authorization]
    Simulation --> Ledger
    Paper --> Ledger
```

These are logical responsibilities, not separate services. NautilusTrader supplies reusable market-event, simulation and execution facilities once compatibility is proven; it does not remove the need to test application portfolio/risk policy. No live adapter is enabled by this design.

| Boundary | Owns | Must not own |
|---|---|---|
| Data | Provider adapters, contract resolution, validation, immutable provenance, calendars, availability and feature snapshots | Strategy decisions or hidden forward fills |
| Research/backtest | Experiment configuration, folds, trials, cost/fill models, engine replay and metrics | Credentials or promotion based only on in-sample performance |
| Agents | Rule/model inference and structured proposals using allowed snapshots | Broker calls, final sizing authority or mutable risk limits |
| Coordination | Proposal validation, registered hybrid composition, deterministic conflict policy and allocations | Implicit confidence normalization or bypassing risk |
| Portfolio | Fill-based positions/cash/PnL, pending exposure, currency and agent attribution | Treating a submitted order as a fill |
| Risk | Configured limits, reservations for pending orders, eligibility, stale-data checks, halt and approval/rejection | Predictions, LLM interpretation or automatic limit changes |
| Execution | Approved-intent deduplication, account/mode validation, order lifecycle and reconciliation | Accepting raw proposals as orders |
| Analytics | Read-only Parquet/DuckDB research, comparisons and reporting | Sole durable order/position recovery state |

## Extension interfaces

Treat provider, instrument, strategy and execution as independent configuration axes. Small modules hide provider parsing, corporate actions, calendar/availability validation and broker lifecycle behind interfaces shared by their callers/tests. Use explicit dependencies rather than constructing vendor clients inside a strategy. Add an adapter or instrument configuration when an actual variation needs it; implement no plugin registry, distributed bus or universal market framework now.

| Extension | What may change locally | What stays shared |
| --- | --- | --- |
| Historical provider/feed | Fetch/parser adapter, query/rights metadata, timestamp semantics and fixture coverage | Validated observations, native catalog, causal snapshots and strategy consumers |
| Instrument | Effective identity/mappings, currency, increments, multiplier, sessions and product-specific actions/capabilities | Normalization invariants, configured strategy logic, portfolio/risk interfaces |
| Strategy | Registered policy and its parameters/state, detector/feature use and tests | Versioned proposals, final sizing/risk, execution lifecycle |
| Execution broker | Contract/order translation, connectivity and reconciliation adapter | Approved intents, account/risk preflight, fill/fee events and central ledger |

Data symbols are not broker contract IDs. Historical feed and live execution venue need explicit mapping and compatibility evidence; selecting IBKR does not require IBKR history. Initial real configuration admits NVDA only; a second synthetic instrument/source proves extensibility without enabling another market. New product semantics require explicit capability/schema versioning and regression tests rather than weakening validation. [REQ-ARCH-002](../REQUIREMENTS.md) owns the measurable checks; [NVDA plan](data/NVDA_DATA_PLAN.md#modular-extension-contract) owns data details.

## Minimal integration contracts

Data exposes validated point-in-time observations keyed by instrument and availability time. Agent inputs contain a decision clock, data snapshot references and frozen rule/model configuration. Agents return the [proposal contract](AGENT_ARCHITECTURE.md#proposal-contract); they do not place orders.

Portfolio policy converts eligible directional proposals to candidate position changes under explicit sizing/allocation rules. Risk checks aggregate filled **and pending** exposure, reserves approved capacity, and produces an identified order intent bound to the account, mode, instrument, size, price/order constraints, expiry, proposal IDs and risk-policy version. Execution rechecks freshness, halt/account identity and reservation validity immediately before submission. Approval is invalid if material portfolio/market state changes; revalidate instead of treating approval as permanent.

Execution events carry intent/order IDs, broker acknowledgements, fills, cancel/reject events and fees into the single-writer portfolio ledger. Partial fills and cancel/fill races update reservations. Unknown submission outcomes halt new risk until reconciliation; retry does not imply a second order. Multi-agent research starts with synchronous ordered evaluation, not distributed consensus.

## Candlestick recognition and policy boundary

Planned M3b data flow: validated completed/available candles and causal aggregation → reusable deterministic pattern observations → configured rule confirmations/entry/exit policy → existing RULE proposals → shared portfolio/risk/execution. Later ML consumes the same observations as causal features. The detector owns shape calculations, input cutoffs and provenance; it owns no positions, sizing, order lifecycle or training. Rule policy owns directional interpretation and proposed entry/exit/stop/target constraints referenced by the common proposal; portfolio/risk validates and authorizes actual intents.

Keep recognition, trading policy and feature consumption separable with small components/functions using existing validated data and Nautilus facilities. No new service, agent family, TA dependency or executable module is introduced by this design. Higher-timeframe buckets are unavailable until complete and all required constituents are available; missing/partial buckets, future pivots and stitched expiry prices cannot become earlier features. [Candlestick specification](CANDLESTICK_AGENTS.md) owns precise definitions, configuration, proposal mapping and measurable gates; this diagram does not claim those components already exist.

## Time, instruments and storage

- Internal timestamps are timezone-aware UTC; US cash-window definitions use `America/New_York` and a versioned calendar. CME trading sessions are not identical to US cash sessions. Preserve event time, bar start/end, availability, acquisition time and vendor timezone semantics.
- Historical acquisition often occurs years after an event. Backtests use defensible simulated historical availability (bar completion plus declared delivery latency), while separately retaining actual acquisition time. Current downloads do not prove point-in-time revision history. Uncertain availability is recorded and sensitivity-tested, never silently asserted causal.
- Use a stable instrument identity with separate provider/broker mappings and effective price/quantity/currency/session metadata. For NVDA, preserve raw execution prices/shares and corporate actions; construct split-neutral signal returns explicitly. Expiry/roll validation belongs to future admitted futures and the retained MES fixtures, not to every equity. Continuous/adjusted research series cannot supply executable fills without a declared transformation back to raw units.
- M2 introduces ignored `data/raw/`, `data/curated/` and optional `data/catalog/quantlab.duckdb`; manifests/configuration without licensed data may be versioned. Parquet snapshots are immutable/versioned; corrections create new versions. Dataset rights govern archiving and redistribution.
- Model artifacts, scalers, prompts and inference outputs have version/hash provenance and data cutoffs. Keep large artifacts outside Git. Text must distinguish publication, ingestion and revision times; a current LLM may have memorized future information relative to a historical test, which must be disclosed and evaluated.

## Modes and reliability

Historical mode uses an explicit simulated clock and execution model. Paper mode consumes approved real-time feeds and a strictly allow-listed paper account. Share proposal/portfolio/risk semantics while testing actual differences in timestamps, fill behavior and broker support; parity is a goal, not assumed equivalence.

Before M6, choose a minimal durable journal/recovery mechanism based on verified framework capabilities. Recovery loads durable intents/events, queries broker state and reconciles positions, open orders and fills before resuming. Logs are sanitized and correlated by run/agent/proposal/intent IDs. Missing state, feed loss, stale advisories, clock anomalies or unknown orders fail closed for new risk. A kill switch blocks new exposure and follows an explicit cancellation/liquidation policy; it cannot promise immediate fills during an outage.

## Staged construction

M1 proves a coherent released Python/NautilusTrader/API/docs tuple offline; `latest` documentation is insufficient version evidence. M2 builds data integrity. M3a proves the initial ITSM agent with minimal shared risk, portfolio and historical execution; only after that baseline, M3b adds reusable candlestick recognition and independently evaluated rule variants. M4 is a future separately authorized ML evaluation after rule research is assessed; it uses the same proposal interface and may reuse causal pattern features. M5 independently validates candidates before any M6 paper promotion. M6 alone adds approved paper connectivity and operational risk/recovery. M7–M9 add simultaneous agents, LLM advisory and expansion. M10 evaluates conditional live readiness under separate authorization. See [ROADMAP.md](ROADMAP.md) for gates and exclusions.
