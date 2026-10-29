# Decision log

Reconciled 2026-10-29 from the handoff and the user's initialization task. **Adopted** means selected direction; **provisional** requires evidence; **deferred** means no choice yet. No entry authorizes trades or spending.

| ID | Status | Decision and reason |
|---|---|---|
| D-001 | Adopted | One modular quantitative platform with shared data/portfolio/risk/execution; avoid three disconnected systems. |
| D-002 | Adopted | Rule-based, ML and LLM agent families; hybrids compose proposals. Agent family is independent of asset/horizon/mode. |
| D-003 | Adopted | Repository `quant-trading-lab`, Python package `quantlab`, intended hosting/CI GitLab. Actual `origin` is GitHub; no migration or remote changes during initialization. |
| D-004 | Adopted | Immutable source data plus curated Parquet; DuckDB analytical catalog, pandas/Polars by need. DuckDB is not the operational order ledger. |
| D-005 | Provisional | NautilusTrader is preferred; choose a coherent released Python/framework/adapter/docs tuple and pass M1 offline tests. Latest documentation may describe a different release line. |
| D-006 | Adopted | Interactive Brokers is selected for eventual paper trading and initial historical feasibility. Alpaca is a future alternative, not a selected MES broker. Account/API permissions remain unverified. |
| D-007 | Adopted | Source-neutral historical data, IBKR first. Databento optional only after measured coverage/quality gaps, rights review, quote and approved spending. No mandatory additional vendor. |
| D-008 | Adopted | First instrument CME MES, actual expiring contracts and USD accounting; leverage and margin do not cap losses. |
| D-009 | Provisional | EXP-001 sign-agreement momentum adaptation: previous cash close→10:00 and 15:00→15:30 ET; entry after data is available, exit target 16:00. Not an established paper replication or demonstrated alpha. |
| D-010 | Adopted | ML is early core research (M4) after reliable data and rule baseline; scikit-learn, LightGBM/XGBoost candidates. Negative results satisfy a completed experiment; promotion needs evidence. |
| D-011 | Adopted | LLM research family is later (M8), advisory, point-in-time auditable and isolated from broker authority. No LLM vendor/tool framework selected. |
| D-012 | Adopted | All families pass a non-bypassable deterministic risk gate. Agents propose; portfolio/risk authorizes intents; execution handles broker lifecycle. |
| D-013 | Adopted | Historical simulation → statistical review → explicitly approved paper; future live readiness is separate and never automatic. |
| D-014 | Adopted | Local Python research first; pytest and future GitLab CI; no compulsory GPU, VPS, colocation, cloud, Redis, Kubernetes or microservices. |
| D-015 | Deferred | Additional equities/futures/crypto/FX, venues/currencies and horizons require separate admission checks and evidence (M9). |
| D-016 | Deferred | Durable execution state design selected before M6 based on tested framework recovery. No new operational database chosen during documentation. |
| D-017 | Adopted | Separate explicit approval before spending, broker connectivity, paper-order activation or live-money capability; public documentation research is permitted now. |
| D-018 | Adopted | Preserve published commits: remote `main` confirmed at `a4c4670afcb982df3d2c28edebbe9635f0b716b1`; one normal local cleanup commit, no reset/amend/force-push. Archives remain in old history. |
| D-019 | Adopted | Isolated Obsidian namespace `Memories/Projects/Quant-Trading-Lab/`, matching the discovered vault's `Memories/Projects` convention. Repository is authoritative; other projects/global notes are untouched. |

## Reconciliation and consequences

The user's current task supersedes archived prompts asking to leave the repository uncommitted: a final local commit is explicitly requested. Its M0–M10 numbering also supersedes the handoff's older combined ML/validation roadmap; ML remains M4, validation M5 and paper M6. Risk tests begin in historical simulation M3, before paper connectivity. Preserve these IDs when refining tasks.

Published history prevents a single root initialization commit without rewriting history. One new initialization commit cleans the final tree; it cannot erase the old ZIP blob. Do not claim the archive was purged from Git history. A future GitLab migration can preserve that history with a normal push when authorized.

The standalone `firstResearch.md` is a condensed editorial derivative, not a byte duplicate of original report 01. Preserve its useful cautions about costs, timestamps, sizing, optional validation complexity and paper fills in the consolidated documentation before removing the redundant file. See [provenance](research/README.md).

## Evidence and open decisions

Official provider/regulator documentation governs current specifications; original papers govern reported study methodology; preregistered out-of-sample experiments govern our own evidence. Gemini reports generate hypotheses and may contain errors. See [synthesis](RESEARCH_SYNTHESIS.md) and [provider verification](COSTS_AND_PROVIDERS.md) for dated citations.

No capital, numeric trading limits, data subscription, tax jurisdiction, historical vendor purchase, profitable strategy or winning model is selected. Resolve these in the relevant milestone. Add focused decision records only when a material trade-off is made; changes to adopted direction require an explicit recorded rationale and user agreement.
