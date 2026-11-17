# NVDA historical archive

Authorized scope, 2026-10-30: **collect and validate raw NVDA 1-minute SIP bars for 2020–2025**. Backtesting was deferred during collection and has since resumed through the [research framework](../BACKTESTING.md) under D-034. Paper execution is unchanged. No paid service, subscription, commit or push.

## Storage and resume

Private archive: `data/nvda-history/`. `index.json` selects verified immutable datasets beneath `year=YYYY/month=MM/curated/<dataset-id>/`. Each month retains original responses/checksums, request attempts/checkpoints, explicit calendar, quality report, native Nautilus catalog and typed Zstd `bars.parquet` for DuckDB. Failed/incomplete requests remain cached, never marked complete. Read the index rather than globbing every historical publication, which could count older versions twice.

```sh
.venv/bin/python -m drift.data.history fetch \
  --root data/nvda-history --start-month 2020-01 --end-month 2025-12 \
  --credentials-file ~/Documents/finance/investor-ai/.env \
  --authorize-historical --store-only --max-gib 2 --min-free-gib 5

.venv/bin/python -m drift.data.history check --root data/nvda-history
```

Downloads are sequential, paced to at most two requests/second, with three seconds between months. Each monthly invocation has a 40-attempt/120-second budget and bounded retries. Completed months/sessions resume from cache. Storage checks run before batches, receipt writes and publication: **2 GiB archive budget**, **at least 5 GiB free**, with publication headroom. Hitting the budget stops collection and preserves validated data. No background scheduler is installed.

## Validation and research isolation

Checks cover raw receipt/inventory hashes, exhausted pagination, explicit `sip`/`raw` requests, ordered/deduplicated minute starts, OHLC/volume/precision, dated cash sessions/DST/early closes, completion/availability times, native/raw/analytical-Parquet agreement and DuckDB duplicate/invalid-row counts. Missing minutes are listed without padding or inferring their cause. Current provider history cannot establish original receipt/revision vintage or complete historical identity/action metadata.

Split metadata preserves raw dollars/shares: 4:1 on 2021-07-20 and 10:1 on 2024-06-10. Cash dividends remain unadjusted. The 2024 effective trading date is supported by [NVIDIA's SEC filing](https://www.sec.gov/Archives/edgar/data/1045810/000104581024000144/nvda-20240607.htm), checked 2026-10-30. This is not certification of every corporate action.

The frozen roles remain **development 2020–2022 / validation 2023 / holdout 2024–2025**. Later-year acquisition and mechanical integrity checks are now authorized; strategy evaluation is not. DuckDB's default view and the combined backtest loader select development only; the engine rejects historical validation/holdout sessions. Do not describe later-year prices as never accessed after acquisition.

```python
from pathlib import Path
from drift.data.history import connect

with connect(Path("data/nvda-history")) as db:  # development only
    print(db.sql("SELECT session_date, count(*) FROM bars GROUP BY 1 ORDER BY 1").fetchall())
```

DuckDB 2.0.0 reads local Parquet directly, using two threads/512 MiB and no extension downloads. Nothing imports InvestorAI; its repository remains unchanged. Account access success does not establish redistribution or indefinite-retention rights; private storage remains subject to account/data terms.

January 2020 first passed the pipeline: **8,190 bars, 21 sessions, zero missing minutes**. Seven untuned one-share baseline diagnostics ran before backtesting was deferred; they use the retained IBKR-reference commission scenario, not Alpaca paper fees. Reports remain under ignored `outputs/nvda-history-first-month/`; no subsequent real-data strategy runs are part of this collection task. 

## Delivered archive — 2026-10-30

All **72 requested months** are stored: **585,897 raw SIP bars / 1,508 cash sessions**, from **2020-01-02 through 2025-12-31**. The collector's final raw/native/analytical/SQL check passed with **zero duplicates and zero invalid rows**. Missing source minutes remain explicit; causes are not inferred.

| Year | Sessions | Bars | Missing minutes |
|---|---:|---:|---:|
| 2020 | 253 | 98,252 | 58 |
| 2021 | 252 | 98,095 | 5 |
| 2022 | 251 | 97,710 | 0 |
| 2023 | 250 | 97,140 | 0 |
| 2024 | 252 | 97,740 | 0 |
| 2025 | 250 | 96,960 | 0 |

Disk allocation is approximately **255 MiB**; more than **12 GiB remains free**. The storage stop was not reached. Source observations require four or six decimals: the December 2021 source contains a six-decimal high. Its exact value survives raw reconstruction, native Parquet and mixed-schema DuckDB queries; the executable tick remains $0.01. Observation precision is not an order-price increment.

The development-only composed dataset loads **294,057 bars / 756 sessions**, promotes source precision without rounding and retains the 2021 split context. No strategy was run for this composition check. Later-year raw prices were acquired and mechanically checked, not used for strategy outcomes.

Software verification: **442 socket-disabled tests passed**, Ruff format/lint, strict mypy, locked offline dependency checks and original research checksums passed. The 264 warnings are upstream Nautilus/pandas deprecations. `data/nvda-history/validation.json`, `coverage.csv` and `gaps.csv` hold the final audit; monthly `quality.json` files retain minute-level provenance and gap details. Complete historical identity/action certification, original revision vintage and unrestricted retention/redistribution rights remain unproven. This is delivered-data/integrity evidence, not full research acceptance or profitability.

No further backtests, orders, paper-code changes, purchases, commit or push followed the owner's data-first instruction. InvestorAI remains unchanged. All five existing Quant Trading Lab Obsidian notes are updated; repository evidence remains authoritative.
