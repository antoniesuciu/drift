# Quant Trading Lab — handoff for browser Codex

**Prepared and scope-aligned: 2026-10-30.** This is a standalone account of the project, the work completed, and the latest user decisions. Keep the next steps focused and practical.

## 1. The final choice

| Item | Confirmed decision |
| --- | --- |
| Initial instrument | **NVIDIA ordinary shares — NVDA** |
| Historical market data | **Alpaca**, preferring free historical SIP data |
| Broker for eventual paper/live execution | **Interactive Brokers — IBKR** |
| Crypto | **Out of scope for now**, including research, ingestion and execution |
| Initial approach | One instrument, one rule-based baseline, realistic costs and chronological validation |
| ML/LLM agents | Future capabilities; defer model selection until rule-based research has been evaluated |

The user explicitly settled on Alpaca + IBKR + NVDA after reviewing the audit. Do not reopen the broker/data comparison or substitute AAPL, SPY, MES, Binance or Coinbase as the active scope. Comparisons involving those products are retained research, not current recommendations.

This choice does not establish profitability, account eligibility, short permission, or authorization to connect accounts or place orders. The eventual live-data feed/entitlement has not been selected or tested; free historical access is not a real-time SIP subscription.

## 2. Where the repository stands

- Repository: `quant-trading-lab`; local branch: `main`.
- Base commit before scope alignment: `376009101a213d680f44d1a800552f4f2feedebb` — `docs: plan candlestick pattern trading agents`.
- Package: `quantlab`, under `src/quantlab/`.
- The audit is included in the scope-alignment documentation: [PROJECT_AUDIT.md](PROJECT_AUDIT.md).
- The user has now authorized one local commit containing the audit, this handoff, active NVDA plan and related requirements updates. Check Git for the resulting commit; this document does not embed its own commit hash. No push is authorized. A browser checkout of the remote may lack these updates; upload the current documents or provide their contents separately.

**Specifications are aligned; implementation is not yet adapted.** README, requirements, architecture, decisions, roadmap and EXP-001 now use NVDA/Alpaca/IBKR with an explicit modular extension contract. [NVDA_DATA_PLAN.md](data/NVDA_DATA_PLAN.md) owns current data gates. Earlier MES planning documents are marked historical/inactive; actual code/tests still implement the synthetic MES pipeline. Preserve that evidence and adapt narrowly when authorized; do not resume MES acquisition.

## 3. What we have built

The working foundation uses **Python 3.12, NautilusTrader 1.231.0, uv 0.13.6, PyArrow 26.0.0 and tzdata 2026.6**. Dependencies are locked in `uv.lock`; pytest, Ruff and mypy are configured. DuckDB is a possible analytics tool, not a required installed service or operational ledger.

The implemented pipeline is:

```text
Local synthetic Databento DBN definitions/bars
  → native Nautilus decoding
  → normalization, identity/calendar/time/gap validation
  → immutable native Parquet catalog + provenance/manifests
  → order-free Nautilus replay
```

| Existing component | What it actually does |
| --- | --- |
| `src/quantlab/time.py` | Validates candle completion/availability and aware timestamps |
| `src/quantlab/data/model.py` | Strict synthetic MES configuration, contracts, sessions and roll rules |
| `src/quantlab/data/databento.py` | Native DBN decoding plus raw identity, precision and checksum checks |
| `src/quantlab/data/core.py` | Normalization, duplicates/gaps, coverage and causal decision snapshots |
| `src/quantlab/data/store.py` | Immutable catalog publication, raw/curated hashes and provenance verification |
| `src/quantlab/data/replay.py` | Real engine callbacks at modeled availability, with zero orders |
| `tests/` | Offline behavior, timing, calendar, integrity, replay and failure cases |

The demo replays **2,160 synthetic bars with zero orders and zero positions**. Limits currently include 32 MiB per compressed/decompressed file, 100k records/file, 100 chunks/request and 250k decoded bars/dataset. Full-history scalability has not been demonstrated.

**Preserve this foundation.** The normalization seam is useful, but current configuration, ticks, quantities, instruments and calendars are MES-specific. An Alpaca reader alone will not make it handle NVDA correctly. Make a narrow adaptation when implementation is authorized; do not relabel stock data as futures or rewrite the platform.

## 4. Completed work versus future plans

| Stage | Actual state |
| --- | --- |
| M0 | Documentation, architecture and original-research preservation completed |
| M1 | Locked environment, package, offline engine smoke and checks completed |
| M2a | Earlier MES historical-data specification/provider research completed |
| M2b.1 | Synthetic offline historical pipeline completed |
| M2b.2 | Replanned for NVDA/Alpaca; all NVDA-001–010 gates pending; earlier MES requests inactive |
| M2 overall | **Incomplete**; active NVDA gates pending; MES 013/014 remain unmet historical records |
| M3 onward | No strategy implementation, paper activation or demonstrated financial results |

The candlestick planning update added recognition/trading within the existing **RULE** family, after the initial ITSM baseline: bullish/bearish engulfing, hammer/shooting star, morning/evening star, Doji, three white soldiers/black crows and inside bar. Planned timeframes are 1m/5m/15m/30m/1h, with optional trend, support/resistance, volume and volatility confirmations. Detection must remain reusable for future ML features. **None of these detectors or agents is implemented.**

The three-family architecture remains **RULE / ML / LLM advisory**. REQ-ARCH-002 requires independently replaceable data adapters, instrument metadata, strategy policies and execution adapters; provider/broker specifics stay out of shared strategy/risk. NVDA is a configuration, not a shared-code constant. No plugin framework or extra service is required. Rule-only validation/paper review does not require ML implementation. Shared portfolio and deterministic risk controls authorize execution; agents cannot directly place orders or change risk limits. Much of this is documented architecture, not working runtime code yet.

## 5. What the independent audit established

We challenged the three original Gemini reports and the latest supplied report against public broker/API/fee/regulatory/research sources, and inspected the code/tests. Detailed dated evidence is in [PROJECT_AUDIT.md](PROJECT_AUDIT.md).

- **Alpaca is a strong free historical stock-data candidate.** Documentation permits historical SIP queries older than 15 minutes; Basic advertises history since 2016 and 200 requests/minute. Set `feed=sip` explicitly and paginate to completion. Free live streaming is IEX. Actual NVDA completeness and applicable download/storage/reuse rights remain unverified. [Alpaca FAQ](https://docs.alpaca.markets/us/docs/market-data-faq), [bars reference](https://docs.alpaca.markets/us/reference/stockbars).
- **Use IBKR as broker, Alpaca as data provider.** Choosing Alpaca data does not require choosing Alpaca brokerage. IBKR's optional integration imports were checked; no account/server handshake or order lifecycle was tested.
- **NVDA needs correct split handling:** 4:1 first adjusted trading on **2021-07-20**, 10:1 on **2024-06-10**. Preserve raw historical dollars/shares for tick/fee arithmetic and separate adjusted return views. Do not mix adjusted prices with raw share units. [NVIDIA 2021 release](https://nvidianews.nvidia.com/news/nvidia-announces-four-for-one-stock-split-pending-stockholder-approval-at-annual-meeting-set-for-june-3), [2024 FAQ](https://investor.nvidia.com/files/doc_downloads/2024/05/NVIDIA-2024-Stock-Split-FAQ.pdf).
- **No strategy edge is established.** Academic SPY ITSM results do not prove NVDA performance. No evidence justified Gemini's stock rankings or fixed spread/profit assumptions. Fees, spread/slippage, latency, FX and any borrow must be included.
- **No month-old-price trading assumption:** historical archives support backtests. Eventual paper/live decisions require current, entitled data and stale-feed checks.

These are audit findings as of 2026-10-30, not account-specific confirmations or permanent provider guarantees.

## 6. Protocol and remaining inputs

1. **Research split — settled:** the active protocol preserves development 2020–2022, validation 2023, holdout 2024–2025. The audit task proposed development 2020–2023, validation 2024, untouched 2025. The requirements update deliberately retained that original split; the proposed alternative was not adopted. Freeze all remaining parameters before evaluating returns.
2. **NVDA experiment:** EXP-001-NVDA-v1 now defines the planning protocol: split-neutral previous close→10:00 plus 15:00–15:30 momentum, trading the final half-hour. It separates raw shares/fills from research adjustments. Implementation and empirical validation remain pending; choosing NVDA does not validate the rule.
3. **Account and execution:** residence/legal entity, cash versus margin, current day-trading regime, live-data entitlement, short permissions/borrow, fee plan, capital and risk limits are unverified. Do not assume zero intraday borrow or universal PDT treatment.
4. **Data admission:** confirm governing terms, NVDA raw/adjusted semantics, coverage, sessions/early closes/DST and historical availability assumptions before treating observations as backtest-ready.

## 7. Recommended next task

Core specifications now reflect the **confirmed NVDA/Alpaca/IBKR scope**, preserve the original split and define the NVDA protocol. Under the next explicitly authorized task, implement only the narrow offline NVDA adapter/metadata prerequisites, then prepare a separately authorized rights-cleared pilot under NVDA-001–010. Acceptance should include full pagination/hashes, explicit gaps, split-boundary fixtures, completed-candle timing, future-data invariance, native catalog/replay verification and measured resource use.

Only after data admission should one preregistered rule backtest run with gross/net costs, controls, coverage, trade counts and uncertainty. Candlestick work follows the initial baseline. Do not expand into crypto, new brokers, ML/LLM selection, orchestration or deployment.

This handoff supplies context. It does not authorize implementation, data acquisition, account access, subscriptions or orders by itself. Follow the user's next task; do not ask them to reapprove the already confirmed instrument/provider/broker choice.

## 8. Verification and documents to read

Last verified on unchanged application code during the audit: **120 tests passed**, with **36 upstream Pandas4Warning** messages; Ruff formatting/lint and mypy passed. Tests block sockets. Original Gemini checksums passed. These are offline engineering results, not trading performance or proof of a server CI run. Tests were not rerun merely to write this handoff.

Read these repository files if available:

1. [AGENTS.md](../AGENTS.md), [README.md](../README.md), [REQUIREMENTS.md](../REQUIREMENTS.md), [decisions](DECISIONS.md) and [roadmap](ROADMAP.md).
2. [Audit and confirmed scope](PROJECT_AUDIT.md), [architecture](ARCHITECTURE.md), [agent contracts](AGENT_ARCHITECTURE.md).
3. [M1 evidence](M1_FOUNDATION.md), [offline pipeline evidence](data/M2B1_IMPLEMENTATION.md), actual `src/quantlab/` and `tests/`.
4. [NVDA experiment](../experiments/exp001_itsm/README.md), [candlestick plan](CANDLESTICK_AGENTS.md), [active NVDA data plan](data/NVDA_DATA_PLAN.md); earlier MES specifications are historical.

Obsidian context was read only under `Memories/Projects/Quant-Trading-Lab/`. The repository specifications are authoritative; browser Codex may not have vault access. Project notes are maintained only within that namespace. Do not modify other projects, global memory or shared configuration. Keep datasets, credentials and account details out of Git; preserve existing user work. The user subsequently authorized committing all scope-alignment documents locally; pushing and trading remain separately authorized actions.
