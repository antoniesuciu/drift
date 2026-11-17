# Alpaca NVDA feasibility evidence

Historical first-pilot checkpoint. The later 2020–2025 monthly archive, revised bounds/precision handling and current integrity evidence are documented in [NVDA_HISTORY.md](NVDA_HISTORY.md).

Verified locally 2026-10-30. This is a narrow implementation/pilot, not full M2 admission or strategy validation. The user explicitly authorized reading InvestorAI's existing Alpaca credentials and privately storing a few July 2021 development sessions. InvestorAI was inspected read-only and remains unchanged. At this historical-pilot checkpoint no purchases, subscriptions, live feeds, broker connections or orders occurred. Subsequent Alpaca paper account/IEX verification and the broker change are documented in [PAPER_EXECUTION.md](../PAPER_EXECUTION.md); no actual orders have been submitted.

## Implemented

- `data/alpaca.py`: stdlib GET-only transport, explicit SIP/IEX and raw 1Min queries, no recent data, development dates only, 40 total attempts, two retries, 2 requests/second, 10-second socket timeout and 120-second invocation deadline checks. Reads are bounded to 16 MiB/response; deadline checks occur between blocking operations, not an interruptible hard wall-clock timer. Honor quota reset/Retry-After; reject redirects and 401/403 without fallback. Credentials enter headers only; error bodies are not read.
- `data/equity.py`: explicit calendar/identity checks, inclusive API bounds translated to minute starts inside half-open cash sessions, Decimal OHLCV, preserved sub-cent data precision versus the $0.01 order tick, ordered deduplication, conflict rejection, unpadded missing minutes and modeled end-plus-delay availability. Known issuer 4:1 split context stays separate from raw prices/shares; dividends remain unadjusted.
- `data/equity_store.py`: immutable original responses/hashes, request/query/retrieval receipts, raw replay, coverage and native Nautilus Parquet instruments/bars. Complete inventory/hash/raw-to-catalog verification before loading; locked staging and atomic publication. Cache completed session requests; retain successful raw pages on failure and restart the incomplete session. No multi-year downloader or general source framework.
- Backtests: version 2 binds an explicit historical dataset ID, metadata and split configuration to the existing ITSM/Nautilus/risk path. Version 1 synthetic and MES behavior remain supported. Only ITSM is admitted to the historical CLI; other strategies await M3a evidence. Source identity includes feed, raw receipts, transformation/consumer code and dependency versions.

Reuse was adapted from InvestorAI commit `f379dd7`: `alpaca.py` (GET allow-list, bounded API/retries, sanitized receipts), `alpaca_replay.py` (Decimal JSON, quota/Retry-After and validation), `alpaca_source.py::_pages` (token exhaustion/repeated-token detection), and `alpaca_probe.py` (literal credential-file parsing/no redirects). Its daily parser/store and broad corporate-action crawl were deliberately not copied: daily keys cannot represent minute bars, and process dates are distinct from split effective dates. No shared package or new dependency was introduced.

## Actual data and access

| Cash date | Raw SIP minutes | Missing cash minutes |
|---|---:|---:|
| 2021-07-16 | 390 | 0 |
| 2021-07-19 | 390 | 0 |
| 2021-07-20 | 390 | 0 |
| 2021-07-21 | 390 | 0 |

Six successful authenticated GET responses: calendar, current asset metadata, and four bar pages. Preserved response bodies total **171,221 bytes**. Queries use `NVDA`, `feed=sip`, `timeframe=1Min`, `adjustment=raw`, `asof=-`, `currency=USD`, ascending order and a 1,000-row page limit. Each cash request spans 13:30:00–19:59:00 UTC inclusively, representing [09:30,16:00) ET. Production pagination did not occur in this sample; short/overlap/repeated/error pages are tested offline.

Historical SIP access for this exact NVDA slice is verified. Account plan/classification and live SIP entitlements were not queried. IEX is a single-exchange feed, not consolidated SIP; it is explicit and separately identified in storage, never a fallback. No actual IEX download occurred. The frozen 2020–2022 / 2023 / 2024–2025 split is unchanged; no validation or holdout prices were read.

Official sources checked 2026-10-30: [bars semantics](https://docs.alpaca.markets/us/reference/stockbars), [feed/access FAQ](https://docs.alpaca.markets/us/docs/market-data-faq), [Basic historical limits](https://docs.alpaca.markets/us/docs/about-market-data-api). Basic documents historical access excluding the newest 15 minutes; live Basic coverage is IEX. Successful reads do not establish a data license. [Public terms](https://files.alpaca.markets/disclosures/library/TermsAndConditions.pdf) and [customer agreement](https://files.alpaca.markets/disclosures/library/AcctAppMarginAndCustAgmt.pdf) incorporate additional applicable terms: private storage was user-authorized, but exchange/account-specific retention, backup, deletion and redistribution rights remain unverified. No unrestricted or indefinite archival grant is claimed.

## Timing and observed backtest behavior

The 15:29-start minute supplies P(15:30), available at 15:30:01 in the baseline. The next eligible minute-open proxy is 15:31. Default flatten decision 15:58 produces a 15:59 **open** proxy exit. A 15:59-start bar completes at 16:00, becomes available after 16:00 and cannot justify its own closing-price fill. These bar-open proxies are synthetic executable quotes, not measured NBBO or exchange fills; historical corrections and modeled latency remain limitations.

One untuned long-only, one-share ITSM feasibility configuration ran twice on the real slice with identical result hashes and reconciled balances. **Zero simulated orders/trades**: the context session lacked a previous close; all three subsequent sessions abstained for zero/disagreeing return signs. This sample therefore verifies ingestion/decisions/reconciliation but does not exercise real-sample fills. Authored minute fixtures independently exercise native engine trades, split handling and exact entry/exit times. Costs in the generated template are illustrative current demo assumptions, not a verified 2021 fee schedule. No parameters were optimized or additional sessions selected after the outcome.

## Storage and commands

Everything generated stays ignored under `data/alpaca-pilot/` and `outputs/nvda-pilot-feasibility/`. `requests/<request-hash>/` retains raw/checkpoint/attempt evidence; `curated/<dataset-id>/` contains original response files, native `catalog/`, `quality.json`, `manifest.json` and a `COMPLETE` checksum. `verified-run.json` identifies the actual checked dataset/report. Changed code creates a new publication from the same cached receipts without extra API calls. Older publications remain intact.

```sh
uv run --locked --offline --extra ib drift alpaca-fetch \
  --request docs/data/nvda-pilot.json --output data/alpaca-pilot \
  --credentials-file "$HOME/Documents/finance/investor-ai/.env" --authorize-historical
# Use the dataset_path printed above as DATASET; it changes when transformation code changes.
uv run --locked --offline --extra ib drift alpaca-check --dataset "$DATASET"
uv run --locked --offline --extra ib drift backtest --strategy itsm \
  --dataset "$DATASET" --dump-config > data/alpaca-pilot/itsm.json
uv run --locked --offline --extra ib drift backtest --config data/alpaca-pilot/itsm.json \
  --dataset "$DATASET" --output outputs/nvda-pilot-feasibility
```

`uv --offline` controls package resolution, not HTTP access; `alpaca-fetch` is the only network command above. Repeated complete requests use verified local receipts. Do not delete checkpoint locks until their writer is confirmed stopped. Preserve private raw data and do not commit it.

## Remaining gates

Verification at this implementation checkpoint: **379 pytest tests passed with sockets disabled** (baseline 318), Ruff format/lint and strict mypy passed, and locked offline sync/lock/dependency checks passed. The 236 visible warnings come from upstream Nautilus/pandas deprecations. Markdown local links and Git whitespace checks passed; changed files contained no actual Alpaca credential values. InvestorAI remained clean. Nothing was committed or pushed. The owner subsequently dropped the separate handoff and requested paper trading after data readiness; project evidence stays here and in [PAPER_EXECUTION.md](../PAPER_EXECUTION.md), with linked Obsidian state.

NVDA-001/002 retain rights/effective-security-metadata uncertainty. The pilot uses current asset metadata and reviewed equity increments, not a complete historical security master. Split evidence is the [issuer's May 2021 announcement](https://nvidianews.nvidia.com/news/nvidia-announces-four-for-one-stock-split-pending-stockholder-approval-at-annual-meeting-set-for-june-3), including its approval condition; the configured known-by timestamp is a conservative next-day model, not a vendor publication receipt. Full action-window/approval reconciliation is not certified. Split dates/ratios are not inferred from price jumps. Synthetic 4:1/10:1 arithmetic does not validate the real 2024 holdout split.

NVDA-003–006/010 have narrow offline normalization, causal-time, split arithmetic, corruption, native round-trip and engine integration evidence. They are not blanket admission signoff. NVDA-007 still needs the remaining planned pilot sessions/windows; NVDA-008 archive coverage and NVDA-009 acquisition/resource scaling remain pending. A measured cached replay is not an acquisition benchmark. No archive expansion, new strategy result or paper promotion follows automatically.
