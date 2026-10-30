# M2b.1 — offline historical pipeline

**Preserved synthetic MES runtime evidence.** Current real-data planning is [NVDA/Alpaca](NVDA_DATA_PLAN.md). The original M2b.2 handoff and MES gates below are historical; keep the working regressions, and use NVDA-001–010 for new admission rather than resuming MES acquisition.

Implemented 2026-10-29 against [MES-ITSM-DATA-v1](HISTORICAL_DATA_SPEC.md) and the [ingestion design](INGESTION_DESIGN.md). **M2b.1 is complete locally; M2b overall and M2b.2 real-data admission remain incomplete.** No acquisition, vendor account/API access, broker connection, order, strategy or model is implemented. Configuration currently requires `mode=offline`, `synthetic=true` and a `synthetic:` rights reference; acquisition and real-vendor admission fail closed rather than pretending to validate a quote/license.

## Run it

Use the existing locked environment; PyArrow 26.0.0 and tzdata 2026.6 are now direct dependencies, both already present in the M1 environment. No new framework, SDK, database or network service was installed. After provisioning as described in the [README](../../README.md#installation-and-checks):

```sh
uv sync --locked --extra ib
uv run --locked --offline --extra ib quantlab data-demo --output data/offline-demo
```

The command generates **synthetic** DBN bytes and a complete request JSON under `data/offline-demo/synthetic-input/`, ingests them, verifies Parquet round-trip and replays the published catalog. It reports **2,160 bars, 2,160 engine iterations, zero orders and zero positions**, a dataset ID and an observation digest. Rerunning the same command reuses verified immutable files and reproduces the same report under the same code/configuration/software. A changed implementation/lock, raw content, calendar or latency policy produces a new dataset identity.

To ingest a separately constructed synthetic request or replay an existing verified dataset:

```sh
uv run --locked --offline --extra ib quantlab data-ingest --request data/offline-demo/synthetic-input/request.json --output data/offline-demo
uv run --locked --offline --extra ib quantlab data-replay --dataset data/offline-demo/curated/mes_itsm_v1/DATASET_ID
```

Replace `DATASET_ID` with the actual printed hash; it is not a fixed dataset name. No credential is accepted or needed. The original `quantlab smoke` behavior remains available and its implementation is unchanged. The new CLI exposes no download, paper or live mode.

## Implemented responsibilities

| Module | Working behavior |
|---|---|
| `data/model.py` | Strict versioned request schema, bounded inputs, typed contracts/sessions/chunks/observations, explicit UTC conversion using locked tzdata, fixed Monday roll validation and same-contract/as-of return utility. This utility is not an ITSM decision rule. |
| `data/databento.py` | Local compressed DBN preflight, content checksums, raw header/identity/price-unit checks, and actual Nautilus `DatabentoDataLoader` definitions/bar decoding. No historical/live client or custom price decoder. |
| `data/core.py` | Provider-neutral SourceBar normalization, exact decimal/volume checks, deterministic ordering/deduplication, conflicting-revision rejection, separate cash/CME calendar checks, coverage, endpoint audit references and causal input snapshots. |
| `data/store.py` | Content-addressed raw archive, native Parquet catalog plus sidecars, logical identity, file/logical/raw hash verification, publication lock, staging/round-trip checks and atomic publication/retrieval. |
| `data/replay.py` | Loads verified catalog Bars/instruments and runs a read-only Actor in the real Nautilus BacktestEngine, comparing actual callbacks and clocks to persisted availability. |
| `data/synthetic.py` | Small deterministic DBN fixture encoder and explicit calendar scenario. Independent native decoding tests the generated wire representation. No vendor observations are embedded. |

## Input format and integrity boundary

The generated `request.json` is the complete executable schema example; [model.py](../../src/quantlab/data/model.py) owns the exact fields. Unknown fields are rejected, including credentials, alternate schemas/assets/currencies and acquisition settings. Required top-level groups are:

- `version/spec/mode/synthetic/provider/dataset/schema`: v1, MES-ITSM-DATA-v1, offline, true, Databento, GLBX.MDP3 and ohlcv-1m.
- `start/end`, `study_start/study_end`: half-open aware request bounds and inclusive cash dates, with an explicitly supplied preceding cash session. Requests cannot silently widen a chunk. One published request describes a contiguous calendar episode; the two M2a pilot windows can be separate requests/datasets.
- `contracts`: actual expiry month, raw symbol, provider/publisher IDs, activation/last-trade timestamps, USD currency, tick 0.25, multiplier 5, lot 1 and XCME exchange. Canonical identity is `CME:MES:YYYYMM`; native ID is `MES-YYYYMM.CME`.
- `sessions`: every civil date in the bounded calendar, explicit full/early/closed cash classification and aware CME tradable intervals. Never infer a CME trade date from UTC date or a cash holiday. Calendar/version identifiers remain declared **synthetic** evidence, not official full-history calendars.
- `rolls`: explicit consecutive quarterly switches on the first full cash session on/after the fixed Monday convention. A cash closure/early close can postpone the switch; actual expiry is supplied explicitly, not assumed to be Friday.
- `chunks`: safe relative local paths for compressed bars and definitions, expected SHA-256 and requested bounds. Symlink escapes, missing files, changed contents and unsupported publishers/datasets fail closed.
- `delay_seconds`, `calendar_version`, `roll_version`, `rights_ref`: modeled delay in [0,60] seconds (baseline 1, adverse 60), frozen versions and synthetic rights marker. None certifies real latency, coverage or licensing.

Source framing checks accept DBN versions 1–3 as understood by the pinned native reader; fixtures directly verify **v1 definitions and v2 OHLCV**. Each record's publisher/instrument IDs must match the supplied contract and the installed publisher/dataset map; mixed known contracts remain distinct. There is no blanket instrument-ID override. Native decoded definitions must match symbol, expiry, activation, currency, exchange, asset class, tick and multiplier. Definitions must already be available at the chunk start; conflicting definition revisions are rejected, not resolved using future metadata.

Raw integer prices are checked at 1e-9 scale before native two-decimal conversion can conceal an off-tick value. Volume is required by the wire record; no default volume is fabricated. Local DBN compression/metadata framing and record counts are bounded: 32 MiB compressed/decompressed per chunk, 100,000 records per chunk, 100 chunks and 250,000 decoded bars per offline dataset. These are explicit safety limits, **not evidence of full-archive scalability**. M2b.2 must establish pilot resource budgets; archive scale-up may require streaming/partitioned processing before gate 014 can pass.

## Time, gaps and causality

Preserve the vendor's raw interval start and provider-receive aggregation clock. Native decoding shifts to close once; the pipeline asserts the exact shift, reconstructs native `ts_event=bar_end` and sets `ts_init=bar_end+modeled_delay`. Raw nanosecond event values remain exact; ISO configuration timestamps must be aware and have at most microsecond precision, so unsupported fractional digits are rejected instead of silently truncated. Internal comparisons and sidecar timestamps are UTC nanoseconds. New York clock boundaries use the explicitly loaded locked tzdata package, not the workstation timezone.

Rows outside supplied CME intervals or contract lifetimes are invalid. Cash-open/early-close/holiday eligibility is separate. Unknown absent minutes remain unknown, with expected/present/missing counts; known exchange pauses are classified as scheduled closures without padding prices. No absence is promoted to confirmed no-trade evidence. A zero-volume row cannot supply a trade endpoint.

`Dataset.snapshot(day, asof_ns)` exposes only the four decision inputs (previous close, 10:00, 15:00, 15:30), each after availability. It applies known full-session, previous-early-close and first-rolled-session exclusions and checks gaps observable by the decision cutoff. A later missing 16:00 target changes retrospective coverage/outcome status **without changing the earlier input snapshot**. The snapshot clock is clamped at the configured 15:30 decision availability even if called later. This prevents retroactive censorship; it does not produce proposals or compute a trading strategy.

`endpoints.parquet` records keys/times/source references for all five endpoints, with 16:00 explicitly marked `role=outcome`. It duplicates no OHLCV warehouse. Static retrospective data is intentionally not an as-of API; use `snapshot` for causal input access. Coverage retains closed/early/roll/excluded dates and unresolved outcomes rather than hiding them or manufacturing PnL.

## Storage, provenance and recovery

```text
<output>/raw/databento/GLBX.MDP3/<raw_sha256>.dbn.zst
<output>/curated/mes_itsm_v1/<dataset_id>/
  catalog/                  # Framework-owned native Parquet Bars/instruments
  provenance.parquet        # Raw record ordinals, source clock and UTC interval/availability
  contracts.parquet
  sessions.parquet
  coverage.parquet
  endpoints.parquet
  quality.json
  receipts.json
  manifest.json
```

Logical identity covers frozen config, raw hashes, transformation-code hash, dependency lock hash, package/framework/Arrow/Python/tzdata versions. Wheels include the actual `uv.lock` as a package resource so installed execution can preserve the lock reference without a checkout; an unexpectedly absent lock is reported as unavailable rather than invented. Receipts record **local ingestion time**, with vendor retrieval time null; wall-clock receipts are outside logical identity but their actual bytes are hashed in the manifest. Cross-version byte-identical Parquet is not claimed.

The manifest also records the source checkout's Git commit and dirty status when available, outside logical identity. A wheel without a checkout reports these as unknown; actual code/lock hashes remain present. Data generated before committing correctly records the base commit plus a dirty tree and actual transformation hash, rather than claiming uncommitted code came from that base commit alone.

Only one curated price copy exists in the native catalog. Sidecars trace metadata and source record ordinals; raw files remain content-addressed outside the curated catalog. `load_dataset` verifies publication identity, native version, complete file inventory, every file/raw checksum, one-to-one row provenance, logical row hash and row counts before exposing native Bars. Transfer raw and curated trees together; a catalog copied without its raw provenance cannot pass verification.

Malformed/configuration/price/session/identity inputs and conflicting revisions reject the whole dataset before publication; original inputs remain unchanged. This is a conservative partition rejection policy rather than a partial salvage/quarantine writer. Exact duplicates coalesce with reference/count auditing. No last-write-wins revision or silent source blending.

Raw publication uses an exclusive content-addressed link after writing/flushing a temporary file. Dataset publication uses an exclusive per-ID lock, new staging catalog, round-trip/file checks and rename. Failed staging is removed; partial staging cannot be loaded as a published dataset. A crash can leave `.publish-<id>.lock` and/or staging files: **verify the specific writer/process is stopped and inspect state before manual recovery**; the application never steals a lock based on age or assumes a lock file proves a live writer. Published datasets are verified and reused, never appended/overwritten. Filesystem checksums detect corruption, not a maliciously re-signed manifest or independent source authenticity.

## Acceptance mapping and verification

Full suite: **120 passed** in the development environment and again in a fresh non-editable installation reproduced from the lock/cache offline, including all unchanged M1 tests, with pytest sockets disabled. Ruff formatting/lint, strict source mypy, offline lock consistency and installed-dependency validation pass. The wheel includes the new modules and bundled lock; tests execute that installed code in the fresh environment. The upstream Nautilus/pandas `Timestamp.utcnow()` deprecation warning remains visible. No test was weakened, skipped for lack of credentials or replaced by a custom simulator.

| M2a gate | M2b.1 evidence | Still externally dependent / future work |
|---|---|---|
| M2B-001 | Strict config, rejected acquisition/real-data modes, bounds, unknown fields/secrets and no-network tests pass. | Billable-request quote/budget authorization controls are not implemented or enabled. |
| M2B-002 | Actual native synthetic DBN definition/bar decoding, identity/precision, malformed/mixed-unknown ID rejection pass. | Authenticated service, real DBN versions/metadata variations and FirstRate fallback remain unverified/unimplemented. |
| M2B-003 | Single bar-label shift, explicit modeled availability, spring/fall UTC/ET DST and prior-Friday offsets, naive/range/precision rejection pass. | Measured vendor delivery/revision history is unavailable. |
| M2B-004 | Exact endpoints and no stale/future substitution pass; removing the later target leaves the earlier input snapshot unchanged. | Real source boundary comparisons await approved data. |
| M2B-005 | Explicit calendar integrity, overnight trade date, weekend/holiday/early/post-early close, scheduled-pause and DST cases pass. | Complete official historical cash/CME calendar provenance is not supplied or certified. |
| M2B-006 | Fixed Monday/next-full-session rolls, first-session exclusion, distinct prices/identities, quarterly/year boundaries and supplied expiry exceptions pass. | Actual dated vendor contract chain/metadata verification awaits admission. |
| M2B-007 | Raw and normalized tick/OHLC/volume/identity/bounds validation and exact decimal round-trip pass. | Real data distribution/exception review pending. |
| M2B-008 | Exact/overlapping duplicates coalesce; out-of-order rows are reported/sorted; conflicts reject publication. | No empirical vendor-revision policy beyond reject-conflicts. |
| M2B-009 | Every supplied local chunk and expected study cash date is accounted for; empty chunk/unknown gaps and separate input/outcome statuses pass. | Delivered real coverage and genuine no-trade evidence remain unmeasured. |
| M2B-010 | Native Parquet Bars/instruments and sidecars round-trip; actual engine callbacks occur at stored availability; zero orders/positions and deterministic replay pass. | Economic fill/PnL/live parity is outside this gate. |
| M2B-011 | Reuse/independent rebuild, new versions after changes, hash corruption, partial publication and exclusive-writer/crash behavior pass. | Full archive scale and power-loss guarantees across filesystems are not established. |
| M2B-012 | Existing tests plus format/lint/types/dependency checks pass; generated data remains ignored and staged content is reviewed. | Real-data secret/license and external CI execution checks remain separate evidence. |
| M2B-013 | **Pending, not passed.** Synthetic fixture success is not real pilot admission. | Approved exact quote/rights, real pilot files, three-contract metadata and delivered 2022 coverage required. |
| M2B-014 | **Pending, not passed.** No six-year archive was acquired or scale-tested. | Approved 25-contract archive, annual coverage/missingness gates and measured resource budget required. |

Tests live in [test_data_pipeline.py](../../tests/test_data_pipeline.py), [test_data_calendar.py](../../tests/test_data_calendar.py) and [test_data_cli.py](../../tests/test_data_cli.py). The [fixture assumptions](../../tests/fixtures/data/README.md) distinguish generated protocol bytes and synthetic calendars from exchange observations. CI runs the full existing suite plus the explicit data-demo command; no remote GitLab run is claimed.

## M2b.2 handoff at M2b.1 signoff

Subsequent [M2b.2 preparation](M2B2_ACQUISITION_PLAN.md) records the authorized research/planning results. Account-specific quote/rights review, acquisition and real-data admission still require the approvals and evidence identified there. The list below preserves the original handoff.

1. Resolve and approve request-specific pricing, CME/vendor local retention/derived-use terms and the bounded pilot acquisition plan; do not reuse live-plan/update prices as archive quotes.
2. Obtain/version authoritative cash/CME calendars and contract definitions; test actual provider definition/ID/DBN variation with approved pilot artifacts. Add a narrowly reviewed real-data admission mode and an explicit historical-only acquisition boundary only when authorized.
3. Admit the two specified 2022 pilot slices independently, verify coverage/exclusions/resource use and satisfy M2B-013. Mark archive/M2c/full gate 014 pending until separately delivered and verified; lift the offline memory cap only with a tested partition/streaming design and budget.

No M2b.2 action begins automatically. IBKR remains the later broker; this pipeline neither needs nor connects to it. ML/LLM agents, ITSM decisions, paper/live execution, DuckDB and additional providers/assets remain unimplemented.
