# NVDA historical data and admission plan

Adopted specification, **2026-10-30**, `NVDA-SIP-DATA-v1`. Implements the direction in [D-026–028](../DECISIONS.md). **Full admission remains incomplete.** A separately authorized four-session Alpaca pilot, offline validation/native storage and backtest integration now work ([evidence](ALPACA_PILOT.md)); this does not close all gates below. This plan itself grants no account access or acquisition authority. The synthetic MES path remains unchanged ([M2b.1 evidence](PIPELINE.md)).

D-033 authorized bounded monthly **2020–2025 acquisition/storage and mechanical integrity checks**; all 72 requested months are now delivered (585,897 bars; 63 explicit missing minutes) ([archive workflow](NVDA_HISTORY.md)). Later years retain their validation/holdout roles; strategy evaluation remains disabled, and further backtesting is deferred. The earlier pilot records below remain historical evidence rather than the current download limit.

## Scope and frozen periods

| Item | Specification |
| --- | --- |
| Initial instrument | NVIDIA ordinary shares, NVDA, USD; effective identity/share class and vendor/broker mappings recorded separately |
| Historical source | Alpaca stock bars, explicit `feed=sip`, `timeframe=1Min`; free historical access candidate, no paid subscription assumed |
| Execution destination | Alpaca paper (D-032); operational IEX trial is separate from historical SIP admission |
| Study | 2020-01-02 through 2025-12-31, plus prior full cash session 2019-12-31 and declared trailing warmup |
| Development | 2020-01-02 through 2022-12-30 |
| Validation | 2023-01-03 through 2023-12-29 |
| Final holdout | 2024-01-02 through 2025-12-31; no strategy results/tuning before frozen evaluation permits it |
| Initial session policy | US regular cash session, 09:30–16:00 `America/New_York`, explicit holidays/early closes and closures; preserve any returned extended-hours rows separately |
| Initial sizing | Configured whole-share research quantities; multiplier 1 from equity metadata. Tick/quantity increments are effective metadata, never inherited from MES |
| Exclusions | Crypto, other real instruments, paid MES acquisition, live-feed activation, orders and model training |

The existing split is deliberately retained while changing instrument/provider. The audit's 2020–2023 / 2024 / 2025 alternative is not adopted. A later split change requires a new protocol version and disclosure of any prior outcome access.

### Small development-only pilot

Prepare separate bounded requests for **2022-03-07–03-18** (US DST; prior session March 4), **2022-11-21–12-02** (holiday/early-close handling; prior session November 18), and **2021-07-19–07-23** (4:1 split; prior session July 16). Dates are inclusive cash dates; translate each into explicit UTC request bounds using the dated calendar and retain required prior-close inputs. The 2024 10:1 split is first covered by synthetic/issuer-based fixtures; any later holdout-data quality inspection follows predetermined integrity rules and excludes strategy returns. The user authorized a smaller first sample: July 16/19/20/21, 2021; all four were retrieved as raw SIP minutes, with 390 bars each. At that checkpoint the remaining sessions/windows were pending and validation/holdout prices were unaccessed. D-033 subsequently delivered all requested archive months, including those pilot windows; later years were acquired for storage/mechanical integrity only. Detailed gap/coverage evidence is in [NVDA_HISTORY.md](NVDA_HISTORY.md); no later-year strategy evaluation occurred.

## Provider interface and reproducibility

The Alpaca adapter owns HTTP pagination, authentication handling, feed/query parameters, timestamp interpretation and raw response capture. It produces validated observations and instrument/action references for the shared normalization/catalog path; strategies never call Alpaca or parse HTTP responses. Use the existing native catalog/replay facilities. Implement small functions/interfaces only when authorized work needs them; no plugin registry, microservices or general vendor framework is required.

1. **Access and rights:** verify the actual data-only account/region entitlement and applicable personal research, raw/derived storage, backup and retention terms. Capture non-sensitive agreement versions/approval references; public API availability is not a license. Keep keys, account identifiers and confidential terms outside Git and memory.
2. **Explicit requests:** record symbol mapping date, feed, timeframe, `adjustment=raw`, bounds, page limit, pagination sequence and retrieval time. Stock bars bounds are inclusive; map them to an internal half-open interval and deduplicate overlapping pages without losing boundary bars. Follow `next_page_token` to exhaustion even after a short page; repeated/missing tokens or failed pages leave the request incomplete. No fallback from SIP to IEX.
3. **Bounded retrieval:** Basic documents 200 historical requests/minute and up to 10,000 total bars/page. Use configurable rate/retry/deadline budgets, backoff and resumable checkpoints; honor response limits. A zero-cost source is not authorization for unbounded requests. Record actual bytes/time, not promised download speeds.
4. **Raw and curated data:** retain permitted immutable raw responses/checksums, request receipts and versioned native catalog rows with provenance. Include canonical instrument, provider symbol, feed, adjustment/action policy, interval start/end, availability kind/delay, calendar, transformation and software versions. Identity/configuration changes create a new dataset; unknown revisions cannot overwrite earlier emitted decisions.

Alpaca's documented `asof` selects symbol mapping, not a historical corporate-action/data vintage. Historical SIP and real-time IEX are different feeds. Raw SIP data can contain condition-based omissions and later revisions; retrieval time does not prove historical receipt time. These limitations belong in the manifest and research report.

## Time, actions and quality

- Preserve a minute's raw start label and exclusive end. Publish usable data only after completion and declared availability; model availability as `end + configured_delay` until measured latency exists. Keep baseline 1-second and adverse 60-second scenarios explicit research choices, not provider guarantees. A next-bar open already passed at availability is not an eligible retrospective fill.
- Use aware UTC internally and a versioned NYSE cash calendar in New York time. Missing minutes remain unknown unless justified by source/calendar evidence; distinguish scheduled closure, confirmed no-trade evidence and missing delivery. Do not pad prices for executable fills or infer SIP from rough volume thresholds.
- Preserve raw historical dollars and shares for fills, ticks and fees. Store a separately versioned split-neutral view/action transform for returns. NVDA 4:1 first adjusted trading **2021-07-20**, 10:1 **2024-06-10**; record effective times, factors and available evidence. Never combine adjusted prices with raw quantity/fee assumptions.
- Across an effective split, express the previous close on the current share basis using an action known by the decision. Unknown required actions make the input unavailable. The first baseline uses split-neutral **price** returns; cash dividends remain in the overnight price return, rather than silently switching to total returns. Alternative adjustment policies need separate trials.
- Validate OHLC, effective tick/quantity precision, nonnegative volume, identity/session membership, ordering, duplicates and revisions. Identical duplicates may merge provenance; conflicting values fail or quarantine under a frozen policy. Split-related price moves are not generic invalid-OHLC errors.
- Report **decision inputs** and **later outcome** readiness separately. A missing later close may make realized PnL unresolved; it must not retroactively remove an earlier valid decision. Preserve the existing causal snapshot/future-invariance principle.

## Modular extension contract

Keep four independent configuration choices: **data adapter/feed**, **instrument metadata**, **strategy policy**, **execution adapter**. Broker contract lookup and order acknowledgements stay in execution; provider symbols/adjustments stay in data; strategy intent uses the [common proposal](../ARCHITECTURE.md#proposal-contract); shared portfolio/risk owns quantities and limits.

A later source or instrument supplies its own mapping, units, calendar, actions and capability checks through the same interface. Add product-specific validation where needed, with regression coverage and version changes when semantics genuinely differ. Configurability is not automatic admission. Existing synthetic MES fixtures can remain a second source/instrument regression case; they are not another active market. No shared normalizer or detector should contain a trading-policy branch for the string `NVDA`.

## Acceptance gates

| Gate | Required measurable evidence |
| --- | --- |
| NVDA-001 — request/rights | Approved exact pilot bounds/feed/adjustment and applicable access/rights evidence; every page/request accounted for, failed requests never marked complete |
| NVDA-002 — identity/units | Effective equity metadata and mappings verified; no MES tick/multiplier/calendar leakage; two synthetic instruments with different increments/units pass through shared validation |
| NVDA-003 — source normalization | Alpaca fixtures cover inclusive bounds, pagination overlap/short/repeated pages, revisions and errors; equivalent observations through two source adapters have equal market values/times with distinct source lineage |
| NVDA-004 — causal time | Exact start/end/availability, late last component, future-data invariance, DST, holidays and early closes tested; no observation or fill precedes availability |
| NVDA-005 — actions | Hand-calculated 4:1 and 10:1 examples preserve share/value arithmetic and split-neutral returns; unknown action abstains; raw execution and adjusted views cannot be mixed |
| NVDA-006 — immutable replay | Raw hashes, complete native catalog/provenance inventory, normalized round-trip and fresh-engine order-free replay agree; changed raw/config creates new identity; corruption/incomplete publication fails closed |
| NVDA-007 — real pilot | All three development pilot windows plus prior-session context are delivered or explicitly failed/quarantined; every requested session/gap/action accounted for; no synthetic observations substitute for missing real data |
| NVDA-008 — archive coverage | Separately authorized 2020–2025 archive has at least 95% data-complete eligible full cash sessions **in each year**, with all missing/excluded sessions and decision/outcome readiness reported. This is a data gate, not paper promotion |
| NVDA-009 — resources | Pilot wall time/peak RSS/storage measured; numeric budgets agreed before archive scale-up; bounded monthly publications preserve prior-session context, cross-partition identity/dedup and a global coverage/manifest index |
| NVDA-010 — reproducibility/extension | Same admitted input/config/code reproduces logical catalog/replay outputs; adding a synthetic source/instrument changes adapter/config/metadata, not strategy/risk policy. Existing MES tests remain meaningful; new admissions do not inherit their pass status |

NVDA-001–007 and pilot evidence of 009–010 precede real pilot signoff; 008 and archive evidence of 009–010 precede full M2 signoff. Offline portions can pass before real acquisition, but cannot satisfy delivered-data gates. Historical MES gates 013/014 remain unsatisfied historical records; they are not silently renamed or required purchases for NVDA.

## Sources and current limitations

Official pages rechecked **2026-10-30**: [bars request/pagination/adjustments](https://docs.alpaca.markets/us/reference/stockbars), [feed/timestamp FAQ](https://docs.alpaca.markets/us/docs/market-data-faq), [plans](https://docs.alpaca.markets/us/docs/about-market-data-api), [public terms](https://files.alpaca.markets/disclosures/library/TermsAndConditions.pdf), [customer agreement §30](https://files.alpaca.markets/disclosures/library/AcctAppMarginAndCustAgmt.pdf). Public jurisdiction/retention uncertainty is detailed in the [audit](../archive/audit/PROJECT_AUDIT.md); the original four-session pilot verified access for its slice; D-033 now verifies delivered historical NVDA SIP access across all requested 2020–2025 months, with explicit gaps ([evidence](ALPACA_PILOT.md)); live entitlement and broad storage rights remain unverified. [NVIDIA 2021 release](https://nvidianews.nvidia.com/news/nvidia-announces-four-for-one-stock-split-pending-stockholder-approval-at-annual-meeting-set-for-june-3) and [2024 split FAQ](https://investor.nvidia.com/files/doc_downloads/2024/05/NVIDIA-2024-Stock-Split-FAQ.pdf) support the action fixtures; actual source mapping/actions still need admission evidence.
