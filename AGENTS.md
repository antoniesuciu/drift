# Working in Drift

## Start a task

1. Inspect Git status, branch and diffs; preserve existing user work.
2. Read [README.md](README.md), the active entry in [ROADMAP.md](docs/ROADMAP.md) and [REQUIREMENTS.md](REQUIREMENTS.md); use [GLOSSARY.md](GLOSSARY.md) for domain terms.
3. Work on one milestone at a time. Scope is NVDA shares / Alpaca historical SIP / Alpaca paper execution (D-032); crypto is deferred. M2 real-data admission remains incomplete: the MES fixture path is preserved; the Alpaca equity path has a four-session raw SIP pilot and ITSM backtest integration ([evidence](docs/data/ALPACA_PILOT.md)). Record scope changes and milestone evidence in the roadmap. An exit gate is evidence, never authorization for brokerage access or deployment.

Read before changing:

- **Interfaces or agent contracts:** [ARCHITECTURE.md](docs/ARCHITECTURE.md).
- **Strategies or backtests:** [BACKTESTING.md](docs/BACKTESTING.md), [STRATEGIES.md](docs/STRATEGIES.md), the [EXP-001 protocol](experiments/exp001_itsm/README.md) and [COSTS_AND_PROVIDERS.md](docs/COSTS_AND_PROVIDERS.md). Relative strength, statistical arbitrage and volatility breakout are future work. M3a (ITSM) precedes the other rules as evidence.
- **Execution or paper safety:** [PAPER_EXECUTION.md](docs/PAPER_EXECUTION.md). Alpaca is now the active paper broker: fixed paper REST host, free IEX operational data, bounded ITSM session runner and shared SQLite gate. The paper account/current IEX bars are verified; usable in-session quotes and actual paper fills remain unverified. IBKR modules are inactive regression groundwork. The owner authorized this paper trial; no spending or live-money authority exists. Preserve historical research gates and distinguish the operational IEX trial from SIP strategy acceptance.
- **Historical archive or DuckDB:** [NVDA_HISTORY.md](docs/data/NVDA_HISTORY.md). Collection/storage/integrity for 2020–2025 is delivered, with a 2 GiB archive budget and 5 GiB minimum free space. Backtests run on development freely, on validation only with an explicit recorded opt-in, and never on holdout (D-034); paper execution stays unchanged.
- **NVDA data, providers or instruments:** [NVDA_DATA_PLAN.md](docs/data/NVDA_DATA_PLAN.md) before implementation or admission. Preserve raw/adjusted share units, completed-candle availability, the frozen research split and native provenance. Choosing a source authorizes no acquisition or account access.
- **The ingestion pipeline:** [PIPELINE.md](docs/data/PIPELINE.md) and [extension interfaces](docs/ARCHITECTURE.md#extension-interfaces). Keep the MES regressions and fixture-only restrictions until an approved admission change; NVDA-001–010 need their own evidence. Keep provider parsing and broker lifecycle out of strategy and risk modules.
- **Historical evidence** (MES procurement, Gemini reports, the feasibility audit): [docs/archive](docs/archive/README.md). It is inactive; consult it for retained MES behavior or a separately requested futures task.

## Development and verification

- Python lives under `src/drift/` with explicit, typed boundaries, instrument and currency identifiers, and validated configuration. Create modules when the active milestone needs them; choose dependency versions from verified compatible releases.
- Add each strategy as its own module under its family (`strategies/rule/statistical/`; `ml/` and `llm/` stay empty until authorized), and keep detection separate from trading policy.
- Cover behavior and failure cases with pytest, using the checks in [README.md](README.md#install-and-check). Tests are offline and synthetic, with no credentials.
- Report the commands you ran and their limitations. When behavior or evidence changes, update the requirements, decisions, experiment protocols and roadmap, keeping each fact in one document, and record significant trade-offs as concise decisions. For documentation, check links, consistency and the actual Git diff.
- Take research facts from original papers and official technical or provider sources, with access dates and uncertainty; use Context7 for current library APIs.

## Research and market data

- Preregister hypotheses, splits, costs and parameters, and record every attempted trial and failed experiment. Synthetic data never counts as measured market performance.
- Prevent lookahead with completed bars, publication and availability times, causal feature transforms and purged overlapping training labels. Refit scalers and models on training folds only; keep the final holdout untouched.
- Preserve raw data and provenance, gaps, effective instrument mappings and increments, equity corporate actions, calendars/DST and vendor timestamp semantics. Futures expiry and roll rules apply to futures; adjusted research series are not raw executable prices.
- Model commissions, exchange and regulatory fees, spread, slippage and multiplier/currency math explicitly; count spread once when fills use executable bid/ask. Paper fills and bar-only simulations have limits.

## Trading and security guardrails

- All families emit versioned proposals through shared portfolio and deterministic risk controls; agents, including LLMs, have no broker access and no authority over risk limits.
- Obtain explicit authorization for paid services, broker connections, paper-order activation and live-money capability. A milestone signoff alone authorizes none of them.
- Keep datasets, credentials, account identifiers, authentication material and generated models or results out of Git. Sanitize logs. Fail closed on stale data, uncertain order state, reconciliation failure or unavailable risk state.

## Memory and Git

- Before substantial work, search Obsidian read-only and verify older claims against the repository. Write durable project knowledge only under `Memories/Projects/Quant-Trading-Lab/` ([PROJECT_MEMORY.md](docs/PROJECT_MEMORY.md)), reading a note before updating it. Other projects, global memory and shared configuration stay untouched.
- Review status and the complete staged diff, stage paths explicitly, and check for secrets and generated data before committing. Commit when authorized, in small descriptive commits. Preserve published history; force-push, unrelated amends and pushes need explicit instruction. GitHub is the host and CI target; inspect the actual remotes before hosting changes.
