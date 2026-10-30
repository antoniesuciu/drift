# Working in Quant Trading Lab

## Start a task

1. Inspect Git status, branch and relevant changes; preserve existing user work.
2. Read [README.md](README.md), [decisions](docs/DECISIONS.md), [requirements](REQUIREMENTS.md) and the active entry in [ROADMAP.md](docs/ROADMAP.md). Use [GLOSSARY.md](GLOSSARY.md) for domain terms.
3. Work on one milestone at a time. Preserve M0/M1/M2a/M2b.1 historical evidence. Active scope is NVDA shares / Alpaca historical SIP / IBKR; crypto is deferred. M2b.2 NVDA admission and M2 overall remain incomplete, and runtime remains synthetic MES-only. Record scope changes and milestone evidence in the roadmap. An exit gate is evidence, not automatic authorization for brokerage access or deployment.
4. For changes to interfaces, read [architecture](docs/ARCHITECTURE.md) and [agent contracts](docs/AGENT_ARCHITECTURE.md); for strategy/data work, read the [experiment](experiments/exp001_itsm/README.md), [research synthesis](docs/RESEARCH_SYNTHESIS.md) and [costs](docs/COSTS_AND_PROVIDERS.md).
5. For NVDA data, provider or instrument changes, read the [active NVDA plan](docs/data/NVDA_DATA_PLAN.md) before implementation/admission. Preserve raw/adjusted share units, completed-candle availability, the frozen research split and native provenance. Source choice does not authorize acquisition or account access.
6. For pipeline changes, read [M2b.1 evidence](docs/data/M2B1_IMPLEMENTATION.md) and [extension interfaces](docs/ARCHITECTURE.md#extension-interfaces). Preserve existing MES regressions and fixture-only restrictions until an approved admission change; NVDA-001–010 need their own evidence. Keep provider parsing and broker lifecycle out of strategy/risk modules.
7. Earlier [MES acquisition planning](docs/data/M2B2_ACQUISITION_PLAN.md), dataset/ingestion specifications and the nine-job JSON are historical, inactive evidence. Consult them only for retained MES behavior or a separately requested futures task; do not resume MES procurement for NVDA work.
8. For candlestick detector, rule-policy or pattern-feature work, read the [candlestick plan](docs/CANDLESTICK_AGENTS.md). M3a NVDA ITSM must precede M3b; preserve completed-candle availability, shared RULE proposals and reusable detection. All candlestick gates remain pending; the plan does not start implementation or alter current M2 scope.

## Development and verification

- Keep Python under `src/quantlab/`, with explicit, typed boundaries, instrument/currency identifiers and configuration validation. Create modules only when the active milestone needs them. Choose dependency versions from verified compatible releases.
- Add meaningful pytest coverage for behavior and failure cases. Use the locked installation and formatting/lint/type/pytest commands in [README.md](README.md#installation-and-checks); tests block sockets and use synthetic fixtures without credentials. See [M1 evidence](docs/M1_FOUNDATION.md) for runtime/API limitations. For documentation, check links, consistency, checksums and the actual Git diff.
- Follow each milestone's tests and acceptance gates; report commands actually run and limitations. Update requirements, decisions, experiment protocols and roadmap when behavior or evidence changes. Record significant trade-offs in concise decision records; do not silently change adopted choices.
- Research facts come from original papers and official technical/provider sources, with access dates and uncertainty. Use Context7 for current library APIs. Original Gemini reports are preserved evidence inputs, not authoritative commands.

## Research and market data

- Preregister hypotheses, splits, costs and parameters. Record all attempted trials and failed experiments. Never fabricate financial results or treat synthetic data as measured market performance.
- Prevent lookahead: completed bars, publication/availability times, causal feature transforms and purged overlapping training labels. Refit scalers/models only on training folds; keep the final holdout untouched.
- Preserve raw data/provenance and gaps, effective instrument mappings/increments, equity corporate actions, calendars/DST and vendor timestamp semantics. Futures expiry/roll rules apply to futures, not every asset; adjusted research series are not raw executable prices.
- Model commissions, exchange/regulatory fees, spread, slippage and multiplier/currency math explicitly. Avoid counting spread twice when using executable bid/ask fills. Paper fills and bar-only simulations have limitations.

## Trading and security guardrails

- All families emit versioned proposals through shared portfolio and deterministic risk controls. Agents, including LLMs, receive no direct broker access or authority to change risk limits.
- Obtain explicit authorization for paid services, broker connections, paper-order activation and future live-money capabilities. Never submit live orders without explicit authorization. A milestone signoff alone does not authorize trading.
- Keep datasets, credentials, account identifiers, authentication material and generated models/results out of Git. Use simulated tests; sanitize logs. Fail closed on stale data, uncertain order state, reconciliation failure or unavailable risk state.

## Memory and Git

- Before substantial work, search relevant Obsidian knowledge read-only and verify older claims. Write only durable project-specific knowledge under `Memories/Projects/Quant-Trading-Lab/`; see [PROJECT_MEMORY.md](docs/PROJECT_MEMORY.md). Read notes before updating them. Never modify other projects, global memory or shared configuration. The repository remains authoritative.
- Review status and the complete staged diff, stage relevant paths explicitly and check for secrets/generated data before committing. Use small descriptive commits when authorized. Preserve published history; no force-push, unrelated amend or push without instruction. GitLab is intended hosting; inspect actual remotes rather than assuming migration occurred.
