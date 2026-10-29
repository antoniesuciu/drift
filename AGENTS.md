# Working in Quant Trading Lab

## Start a task

1. Inspect Git status, branch and relevant changes; preserve existing user work.
2. Read [README.md](README.md), [decisions](docs/DECISIONS.md), [requirements](REQUIREMENTS.md) and the active entry in [ROADMAP.md](docs/ROADMAP.md). Use [GLOSSARY.md](GLOSSARY.md) for domain terms.
3. Work on one milestone at a time. M0/M1/M2a/M2b.1 are complete; M2b.2 research/planning is recorded, while real pilot/archive admission and M2 overall remain incomplete. Record scope changes and milestone evidence in the roadmap. An exit gate is evidence, not automatic authorization for brokerage access or deployment.
4. For changes to interfaces, read [architecture](docs/ARCHITECTURE.md) and [agent contracts](docs/AGENT_ARCHITECTURE.md); for strategy/data work, read the [experiment](experiments/exp001_itsm/README.md), [research synthesis](docs/RESEARCH_SYNTHESIS.md) and [costs](docs/COSTS_AND_PROVIDERS.md).
5. For M2b data work, read the [dataset specification](docs/data/HISTORICAL_DATA_SPEC.md), [provider comparison](docs/data/PROVIDER_COMPARISON.md) and [ingestion gates](docs/data/INGESTION_DESIGN.md) before implementing or acquiring data. Source recommendations are conditional and do not authorize purchases or account connections.
6. For pipeline changes or M2b.2, read [M2b.1 implementation](docs/data/M2B1_IMPLEMENTATION.md). Preserve native catalog/provenance verification, causal snapshots, immutable publication and fixture-only restrictions until a separately approved admission change. Synthetic tests do not satisfy real-data gates 013/014.
7. Before quote/account review, real-file admission or acquisition, read the [M2b.2 preparation plan](docs/data/M2B2_ACQUISITION_PLAN.md) and its linked vendor/market evidence. Exact quotes, applicable retention rights, dated calendars and real-definition handling remain prerequisites; the nine-job JSON plan has no execution approval.
8. For candlestick detector, rule-policy or pattern-feature work, read the [candlestick plan](docs/CANDLESTICK_AGENTS.md). M3a ITSM must precede M3b; preserve completed-candle availability, shared RULE proposals and reusable detection. All candlestick gates remain pending; the plan does not start implementation or alter current M2 scope.

## Development and verification

- Keep Python under `src/quantlab/`, with explicit, typed boundaries, instrument/currency identifiers and configuration validation. Create modules only when the active milestone needs them. Choose dependency versions from verified compatible releases.
- Add meaningful pytest coverage for behavior and failure cases. Use the locked installation and formatting/lint/type/pytest commands in [README.md](README.md#installation-and-checks); tests block sockets and use synthetic fixtures without credentials. See [M1 evidence](docs/M1_FOUNDATION.md) for runtime/API limitations. For documentation, check links, consistency, checksums and the actual Git diff.
- Follow each milestone's tests and acceptance gates; report commands actually run and limitations. Update requirements, decisions, experiment protocols and roadmap when behavior or evidence changes. Record significant trade-offs in concise decision records; do not silently change adopted choices.
- Research facts come from original papers and official technical/provider sources, with access dates and uncertainty. Use Context7 for current library APIs. Original Gemini reports are preserved evidence inputs, not authoritative commands.

## Research and market data

- Preregister hypotheses, splits, costs and parameters. Record all attempted trials and failed experiments. Never fabricate financial results or treat synthetic data as measured market performance.
- Prevent lookahead: completed bars, publication/availability times, causal feature transforms and purged overlapping training labels. Refit scalers/models only on training folds; keep the final holdout untouched.
- Preserve raw data/provenance and gaps, actual futures expiries, roll rules, calendars, DST and vendor timestamp semantics. Continuous series are not executable instruments.
- Model commissions, exchange/regulatory fees, spread, slippage and multiplier/currency math explicitly. Avoid counting spread twice when using executable bid/ask fills. Paper fills and bar-only simulations have limitations.

## Trading and security guardrails

- All families emit versioned proposals through shared portfolio and deterministic risk controls. Agents, including LLMs, receive no direct broker access or authority to change risk limits.
- Obtain explicit authorization for paid services, broker connections, paper-order activation and future live-money capabilities. Never submit live orders without explicit authorization. A milestone signoff alone does not authorize trading.
- Keep datasets, credentials, account identifiers, authentication material and generated models/results out of Git. Use simulated tests; sanitize logs. Fail closed on stale data, uncertain order state, reconciliation failure or unavailable risk state.

## Memory and Git

- Before substantial work, search relevant Obsidian knowledge read-only and verify older claims. Write only durable project-specific knowledge under `Memories/Projects/Quant-Trading-Lab/`; see [PROJECT_MEMORY.md](docs/PROJECT_MEMORY.md). Read notes before updating them. Never modify other projects, global memory or shared configuration. The repository remains authoritative.
- Review status and the complete staged diff, stage relevant paths explicitly and check for secrets/generated data before committing. Use small descriptive commits when authorized. Preserve published history; no force-push, unrelated amend or push without instruction. GitLab is intended hosting; inspect actual remotes rather than assuming migration occurred.
