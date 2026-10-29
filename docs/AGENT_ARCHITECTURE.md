# Agent families and shared proposal contract

Agent is a domain component, not a synonym for LLM autonomy or a separate process. This is a design specification; no agent is implemented in M0. See [architecture](ARCHITECTURE.md) for portfolio/risk/execution ownership.

## Three families

| Family | Inputs and decision mechanism | Candidate examples | Evaluation |
|---|---|---|---|
| Rule-based | Available market observations and fixed deterministic rules/statistics | M3a MES ITSM first, M3b Candlestick Pattern Agents; later ORB, mean reversion, trend, stat-arb, volatility breakout | Replay identity, causal timing, net-cost OOS performance and robustness |
| ML | Causal features and a trained, versioned inference artifact | Logistic regression, random forest, LightGBM/XGBoost; independent predictions or meta-label filters | Fold/label integrity, calibration, drift and net comparison to simple controls |
| LLM | Licensed as-of news, earnings, filings, macro/events and evidence retrieval | Research assistant, event-risk assessment, sentiment/earnings interpretation | Evidence accuracy, temporal validity, injection tests, no-LLM baseline and full costs |

LSTM/Transformers and reinforcement learning are experimental options, not required infrastructure. Hybrids are compositions of these three families. An agent instance has an independent identity/configuration; instrument, horizon and historical/paper mode are separate axes.

## Rule-based candlestick capability

[Candlestick design and acceptance gates](CANDLESTICK_AGENTS.md) plan the 10 pattern forms, configurable instruments and 1m/5m/15m/30m/1h timeframes, optional trend/support-resistance/volume/volatility confirmations and entry/exit/stop/target rules. Recognition produces deterministic observations from completed, available candles; a separate rule policy supplies direction and confirmations. Doji/Inside Bar can remain neutral. The same versioned detection values/cutoffs are reusable as future ML features without a trading policy or broker dependency.

Candlestick agents use `family=RULE` and the proposal contract below, with detector/aggregation/filter/policy and source references carried through existing lineage fields. Shared portfolio/risk alone authorizes sizing and execution constraints. A pattern observation is neither an order nor a fourth family. M3b follows the completed initial ITSM baseline and evaluates variants independently; M5 out-of-sample validation and M6 authorization remain prerequisites for paper use. This is planned behavior; no agent or feature component is implemented by this update.

## Proposal contract

Conceptual schema version 1, to become executable only when M3 needs it:

| Field | Meaning / validity rule |
|---|---|
| `schema_version`, `proposal_id` | Supported schema and globally unique/idempotent proposal identity |
| `agent_id`, `family`, `strategy_id` | Configured producer, one of RULE/ML/LLM, and policy/experiment lineage |
| `instrument_id` | Venue-qualified instrument with expiry/currency metadata; an advisory may reference a configured scope containing instruments |
| `generated_at_utc`, `data_asof_utc` | Creation time and latest availability of any input; both timezone-aware UTC |
| `valid_until_utc`, `horizon_seconds` | Expiry and intended decision horizon; expiry must follow creation |
| `intent` | LONG, SHORT, FLAT, NO_TRADE or ADVISORY; FLAT requests reducing a strategy allocation, not liquidating other agents' holdings |
| `rule_or_model_version`, `input_refs` | Versioned rule/model/feature/prompt references and reproducible source/artifact IDs |
| `rationale` | Short explanation plus evidence references; explanatory prose has no execution authority |
| `score`, `score_semantics` (optional) | Defined meaning and calibration version, never a universal comparable probability |
| `quantity_hint` (optional) | Non-binding suggestion; portfolio/risk determines approved size |
| `parent_proposal_ids` (hybrids) | Complete trace of upstream proposals and registered composition-policy version |

At processing clock `t`, require `data_asof_utc <= generated_at_utc <= t < valid_until_utc`, all referenced input availability times <= generation, and a known instrument/configuration/schema. Historical acquisition time is distinct from modeled historical availability. Reject unsupported schema, malformed/future data, bad lineage and already-consumed IDs. Record reason codes for rejections and abstentions. A duplicate cannot create an additional intent/order.

NO_TRADE is an explicit abstention, not an implicit cancellation. FLAT passes portfolio/risk checks and can only affect the appropriate attributed allocation. M3 evaluates one agent/contract at a time: ITSM first, then independently configured candlestick variants. More complex concurrent netting/attribution is introduced and tested in M7. Risk-reducing requests remain subject to order validity and broker reconciliation.

## Hybrid composition and conflicts

Future example: **Rule momentum proposal → ML accept/reject filter → LLM event-risk advisory → portfolio allocation → central risk → execution**. ML can also emit an independent directional proposal. LLMs emit ADVISORY only; any eventual use of advice is a registered, deterministic, tested composition policy. A positive model score cannot override a risk rejection.

For the initial hybrid policy, a missing/expired/invalid required filter leads to abstention. Optional filters are explicitly declared; omitted advice is never silently converted to approval. Opposite proposals for the same instrument follow a configured policy (initial conservative default: abstain on unresolved conflict), not arrival-order wins. Preserve gross contributions, pending orders and attribution even when net positions cancel. Do not add cross-agent score weighting until meaning/calibration is justified by an experiment.

## LLM trust and evaluation boundary

External text is untrusted data. Restrict retrieval tools to reviewed read-only sources; isolate credentials and portfolio policy. Schema-validate outputs, verify cited evidence exists, distinguish unknown from neutral, and reject instructions embedded in retrieved text. LLMs cannot invoke broker adapters, produce authorized order intents, change risk limits or run arbitrary tools/code.

Archive permissible source snapshots with publication/availability/revision times and record model/prompt/token costs and generated outputs. Deterministic replay uses captured outputs where allowed; repeat API calls are not assumed identical. Later-trained models can leak subsequent knowledge into historical evaluations; use suitable time-bounded evaluation/prospective testing and disclose remaining contamination. Tests cover injection, malformed JSON/schema, invented citations, later publication, stale data, unavailable model and cost-limit exhaustion. Completion measures evaluated research quality and failure behavior; useful trading benefit remains unproven.
