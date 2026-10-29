# MES historical dataset specification — M2a

Specification `MES-ITSM-DATA-v1`, 2026-10-29. **Project policy** below defines a frozen dataset, not measured coverage or market results. Verified external facts have linked primary sources; unverified procurement/delivery questions are listed explicitly. No data was acquired. [Provider comparison](PROVIDER_COMPARISON.md) owns pricing/rights and [ingestion design](INGESTION_DESIGN.md) owns M2b implementation gates. The [EXP-001 rule](../../experiments/exp001_itsm/README.md) is unchanged.

## 1. Dataset tiers and date boundaries

| Tier | Cash-session dates, inclusive | Purpose and required scope |
|---|---|---|
| Pipeline acceptance sample | 2022-03-07–2022-03-25 **and** 2022-11-21–2022-12-02 | Small archive sample spanning March DST change/quarterly roll, Thanksgiving cash closure/early close and the next session. Include prior March 4 and November 18 cash closes. Validate engineering only, not statistical significance. |
| Recommended research archive | **2020-01-02–2025-12-31** | Six complete modern calendar years; include prior full cash session **2019-12-31** as warm-up. Full Globex one-minute bars for the selected outright contract(s), not just five daily endpoints. No 2019 prelaunch interpolation or automatic use of incomplete 2026. |
| Optional execution evidence, later approval | Selected development/validation sessions only, after minute-data adequacy review | Trades plus top-of-book quotes if bar-only fill/cost uncertainty materially affects conclusions. No initial MBO/L2/L3 requirement, tick purchase or full-history quote archive. |

Raw request bounds are half-open UTC: full archive `[2019-12-30T00:00:00Z, 2026-01-01T00:00:00Z)`; pilot `[2022-03-04T00:00:00Z, 2022-03-26T00:00:00Z)` and `[2022-11-18T00:00:00Z, 2022-12-03T00:00:00Z)`. UTC buffers cover the required preceding close and relevant surrounding Globex trading. Partition actual acquisition by contract and calendar month; intersect with that contract's required active-date interval and warm-up, rather than buying every listed MES contract for all six years. Do not request one uncapped parent-symbol history by default.

Freeze the research split before evaluating signals/returns: development/training **2020-01-02–2022-12-30**; validation **2023-01-03–2023-12-29**; final holdout **2024-01-02–2025-12-31**. The 2022 engineering sample is wholly in development. Data-integrity checks may classify holdout gaps using these predetermined rules, but performance/labels/model selection remain inaccessible until the frozen M5 protocol permits them. ML fold refinement is later work, not permission to train here.

MES began trading for trade date May 6, 2019; the target therefore uses no fictitious older MES history. Six years is a useful study design, **not evidence of adequate statistical power**: signal agreement, exclusions and serial dependence reduce effective observations. Report actual eligible-session/trade counts later. [CME launch announcement](https://www.cmegroup.com/media-room/press-releases/2019/5/06/cme_group_announceslaunchofnewmicroe-miniequityindexfutures.html).

## 2. What the academic signal actually is

Gao, Han, Li and Zhou's published SPY study covers 1993–2013 and includes overnight information in its first-half-hour return. [Published research record](https://profiles.wustl.edu/en/publications/market-intraday-momentum/). In the inspectable **June 2017 original-author manuscript**, sections 2–4 define:

- `r1 = P(10:00) / P(previous cash close at 16:00) - 1`;
- `r12 = P(15:30) / P(15:00) - 1`;
- target `r13 = P(16:00) / P(15:30) - 1`.

That manuscript evaluates predictive regressions as well as separate timing rules; equation 5 includes sign agreement. It is not a newly invented project rule. The equation shorts when both predictors are nonpositive, although its prose describes negative values. EXP-001 keeps its already accepted strict-positive/strict-negative, zero-abstention convention. The manuscript's ETF execution and clearing-close treatment do not establish executable MES boundary fills. [Original-author manuscript on a mirror, June 2017](https://assets.super.so/e46b77e7-ee08-445e-b43f-4ffd88ae0a0e/files/ee7dac49-530b-4950-b5d0-e0b5eee08f2e.pdf).

**Evidence limit:** the final author-linked [published-paper copy](https://www.dropbox.com/s/wk5ap8hnvgdyudx/MarketIntradayMomentum.pdf?dl=0) exposed only a preview during review; final full methods/tables were not inspected. The university record corroborates the published core signal, not every manuscript implementation detail. Li et al.'s publisher introduction also includes overnight information, but its exact full trading/cost method was not retrieved. [Li et al., publisher](https://www.sciencedirect.com/science/article/pii/S138641812100001X). Do not label EXP-001 a faithful replication or import reported performance into our acceptance criteria.

Our adaptation uses raw expiring **MES trade-bar closes**, one-minute approximations to boundary prices, explicit information delay, full-session/roll exclusions and realistic subsequent execution. It does not substitute the 09:30 opening price for the previous close, an ES settlement for a MES last trade, or a continuous-series return for a contract return.

## 3. Session and endpoint semantics

Maintain **two calendars**: the US equity cash reference calendar (NYSE core 09:30–16:00 `America/New_York`, with historical holidays/early closes) and the CME MES tradable-session/maintenance/expiration calendar. A futures trading date can start on the prior civil date; preserve `cash_session_date`, `exchange_trade_date` and UTC date separately. CME trading on a US cash holiday does not make that day eligible. Historical unscheduled closures and rule changes must be versioned, not inferred from weekday rules. [NYSE calendars](https://www.nyse.com/markets/hours-calendars), [CME Micro E-mini FAQ](https://www.cmegroup.com/articles/faqs/micro-e-mini-equity-index-futures-frequently-asked-questions.html).

For a chosen contract K and boundary T, define **`P_K(T)` as the close of the populated one-minute bucket `[T−1 minute,T)`** under the provider's declared aggregation clock. It is the last eligible outright trade in that bucket; an exact-T trade belongs to the next bucket. Do not search forward or carry a stale earlier close into an absent bucket.

| Observation | Required New York bucket | Use |
|---|---|---|
| Previous-session close | Immediately preceding cash trading session's `[15:59,16:00)` | Denominator of r1, same K; not a daily bar/settlement |
| 10:00 | `[09:59,10:00)` | Numerator of r1 |
| 15:00 | `[14:59,15:00)` | Denominator of r12 |
| 15:30 | `[15:29,15:30)` | Numerator of r12 and descriptive target denominator |
| 16:00 | `[15:59,16:00)` | Descriptive r13 target numerator; unavailable to the 15:30 decision |

Previous session means the immediately preceding **cash trading session**, not calendar yesterday, not the previous Globex date, and not the latest earlier convenient full session. If either the current session or that immediately preceding session closes early, abstain under existing EXP-001 rules; do not silently skip back another day to obtain a 16:00 price. The 2022 sample contains November 24 closure, November 25 early close and November 28 following-session exclusion; March 14 is both post-DST and the project roll-session exclusion. NYSE's historical notice confirms the November dates; M2b must encode them in the versioned calendar rather than relying on current-year listings. [NYSE/ICE 2022–2024 holiday notice](https://ir.theice.com/press/news-details/2021/NYSE-Group-Announces-2022-2023-and-2024-Holiday-and-Early-Closings-Calendar/default.aspx).

Convert each local boundary independently using a recorded tzdata version. On March 11, 2022, 10:00/15:00/15:30/16:00 ET correspond to **15:00/20:00/20:30/21:00 UTC**; on March 14 they correspond to **14:00/19:00/19:30/20:00 UTC**. On Monday the previous Friday close still uses Friday's winter offset. Reject unresolved naive/ambiguous/nonexistent local timestamps; never apply a fixed UTC offset to the whole study.

The MES settlement is a separate concept: CME's FAQ describes daily settlement from the ES counterpart's 15:59:30–16:00 ET VWAP; final settlement uses a Special Opening Quotation. Neither is `P_MES(16:00)` defined above. No official settlement dataset is required for this signal. [CME FAQ](https://www.cmegroup.com/articles/faqs/micro-e-mini-equity-index-futures-frequently-asked-questions.html), [MES fact card](https://www.cmegroup.com/trading/equity-index/files/cme-micro-e-mini-futures-fact-card.pdf).

## 4. Timestamp normalization and availability

Preserve raw labels and distinguish exchange-event time, provider receive/bucket clock, interval start/end, measured receipt if present, modeled historical availability, and actual retrieval time. Retrieved data can contain later corrections; retrieval years later is not proof of a point-in-time original view.

For recommended Databento `ohlcv-1m`, raw `ts_event` is the **start** of a bucket based on trade-message `ts_recv`; no-trade buckets emit no row. These are receive-clock trade bars, not an independently verified exact exchange-event snapshot. Record `aggregation_clock=provider_receive` and retain the raw timestamp. Daily Databento bars use UTC dates, so they do not supply our previous cash close. [Databento schema](https://databento.com/docs/schemas/ohlcv).

Project baseline for historical replay: `bar_end = bar_start + 60 seconds`; `available_at = bar_end + 1 second`; mark `availability_kind=modeled`, not measured. One second is a **declared simulation assumption**, not a measured vendor SLA. Also support a separately identified **60-second adverse-latency** dataset view without reacquiring raw data. A zero-lag diagnostic is optimistic and cannot be presented as observed latency. Under the baseline, 10:00/15:00/15:30/16:00 prices become usable no earlier than 10:00:01/15:00:01/15:30:01/16:00:01 ET. Every input needed by a decision must already be available.

Nautilus 1.231.0's DBN loader defaults to shifting raw bar labels to completion; historical decoded `ts_init` defaults to completion. Apply the interval shift **exactly once**, then set the normalized Bar `ts_event=bar_end` and `ts_init=available_at` explicitly. A default decoder value is not our modeled delay. Preserve raw label/clock in sidecars. [Pinned integration guide](https://github.com/nautechsystems/nautilus_trader/blob/v1.231.0/docs/integrations/databento.md). FirstRate starts bars in Eastern time; IBKR label semantics require a provider-specific fixture rather than assumptions. See the [comparison](PROVIDER_COMPARISON.md).

The 15:29 bar cannot authorize a fill before 15:30:01. Even the immediately next minute's 15:30:00 open precedes that decision. M3 must use a demonstrably subsequent executable event or a conservative proxy whose timestamp follows the decision; bar-only OHLC paths cannot prove actual fills. Likewise the 16:00 label is descriptive, not permission to inspect that close and retroactively liquidate. Existing scheduled pre-close liquidation/residual policy remains unchanged. This data specification does not implement execution or redefine the strategy.

## 5. Contracts and fixed roll policy

Use individual **quarterly outright MES** contracts (H/M/U/Z), no spreads/options/ES substitution. The full study's active chain runs from March 2020 through March 2026, **25 expiries**, because December 2025 rolls into March 2026 before year-end. The pilot requires March 2022, June 2022 and December 2022. These are expiry-month requirements; actual provider symbols, instrument IDs, listing times and last-trade timestamps must be resolved from authoritative definitions before acquisition.

Canonical key: `CME:MES:YYYYMM`; Nautilus identifier policy: `MES-YYYYMM.CME`, with raw provider symbol retained separately. Keep actual MIC/exchange/publisher and effective-dated provider mappings; project venue `CME` is an alias, not permission to relabel any Globex product. No bare ticker or single-digit year is sufficient identity.

Apply a fixed **Monday before the third Friday** schedule throughout the study, based on CME's currently published equity roll convention, and freeze/version its dates. This is a project scheduling choice, **not a claim that every historical participant/provider rolled on Monday** or a mandatory exchange transaction. Activate the next quarterly contract at **09:30 ET** on that cash roll session; if that cash date is closed/early, use the next full cash session and record the exception. Use actual published expiry/holiday exceptions, not an unconditional third-Friday expiry formula. CME's table, for example, lists June 2026 expiration on Thursday June 18. [CME roll calendar](https://www.cmegroup.com/trading/equity-index/rolldates.html).

M2b.2's [historical verification](M2B2_MARKET_VERIFICATION.md#historical-roll-convention-important-distinction) confirms CME changed ES/MES lead-month rolling to Monday starting June 2022. Keep the frozen March 14 project switch; vendor historical lead/continuous contracts are not a substitute. The same note records dated cash/CME calendar sources and unresolved historical intervals, including the distinct January 9, 2025 closure rules. This adds evidence without changing the specification's dates, roll policy or coverage threshold.

Keep both contracts' bars around the switch for validation, but **exclude the first cash session after the active-contract switch** from EXP-001 because its prior-close interval crosses the active-chain roll. Do not evade that accepted exclusion by looking up the new contract's earlier price. On subsequent eligible dates, every endpoint uses the same selected actual contract. Never divide new-contract price by old-contract price. No actual position rollover is implemented in M2b.

For each contract acquire its active cash dates plus the immediately preceding cash close and the full overlapping outgoing/incoming Globex trading sessions around each scheduled switch (one before and one after), within the global buffers. Request overlapping contracts explicitly only for these checks; retain all returned off-active bars without treating them as selected-series observations. No front-series back adjustment, vendor hindsight volume roll or continuous symbol is the executable source of truth. An optional unadjusted linked view must retain K/date/exclusion lineage; continuous research variants need a separately registered design.

## 6. Required fields and quality rules

Normalized bars must preserve exact decimal/fixed-point OHLC (MES tick 0.25), nonnegative integer contract volume, K, currency, interval, event/completion/availability times, source IDs/clock, raw record reference and dataset/schema version. A populated trade endpoint additionally requires positive volume; an explicit zero-volume vendor row cannot supply an observed-trade price. Databento raw prices are integer 1e-9 units; preserve raw integers and scale without binary-float rounding. Required contract metadata: product/asset class, raw symbol, expiry month, actual last trade/expiration, listing/activation, multiplier 5 USD per point, tick/lot size, venue/MIC and effective mapping. Unknown activation is recorded as unknown with a source-bound justification, never a fabricated date.

| Condition | Required disposition |
|---|---|
| Invalid OHLC ordering, nonpositive MES price, nonfinite value, fractional/negative volume, off-tick price, missing ID or expiry mismatch | Quarantine partition/record; zero unresolved invalid rows in a published dataset. Never silently round, fabricate volume or change product. |
| Exact duplicate `(source,K,interval,bar_start)` | Deduplicate idempotently with raw references and count; no double volume. |
| Same key, different values/revision | Keep raw versions; deterministic version selection requires an explicit revision policy and new dataset version. Never last-write-wins. |
| Missing minute | Classify scheduled closure, supported no-trade interval, vendor gap or unknown. Absence alone does not prove zero trading; no zero-volume/OHLC padding. |
| Missing input endpoint or unresolved gap already observable by decision time | Mark as-of inputs unavailable and record the reason; keep the session in coverage and decision denominators. Do not cherry-pick based on return. |
| Missing post-decision bar/16:00 target/fill evidence | Mark outcome/data-quality unresolved, preserve any earlier decision/trade attempt and exposure, and report missing-outcome sensitivity. Never turn that earlier decision retroactively into NO_TRADE or assign an invented zero PnL. |
| Out-of-order records or overlapping request chunks | Preserve raw order, normalize/deduplicate deterministically and emit a report; replay order is canonical by availability then stable contract/event key. |
| Late corrections/unknown original publication | Preserve retrieval/version lineage and label modeled availability; report historical revision limitation, not certified point-in-time completeness. |

Every expected cash session must have exactly one coverage classification and reason list, with **separate as-of input eligibility and retrospective outcome/quality status**. Full-session target is 390 cash minute buckets, but no-trade omission makes raw row count alone insufficient. A published price endpoint requires its exact populated bucket; unknown gaps are retained, not inferred away. A session with any unresolved required cash-interval gap is not counted as fully data-complete, but that retrospective classification is **not a causal trading filter**. At the 15:30 decision, only already-available information may determine eligibility. Later missing prices leave unresolved outcomes and require explicit sensitivity/bounds or rejection of the research conclusion; dropping them silently would bias the sample. Closed/early/roll/post-early-close exclusions are known calendar policies, distinct from later data failures.

Engineering publication gate: 100% of requested contract/period chunks and expected sessions accounted for, zero unresolved integrity failures in admitted rows, deterministic manifests and explicit gap counts. Confirmatory-study readiness additionally requires at least **95% of calendar-eligible full same-contract sessions in each year** data-complete, with all failures enumerated and unresolved outcomes analyzed separately. This is a preregistered project coverage threshold, not a statistical theorem or permission to censor incomplete outcomes; if unmet, repair/compare sources or transparently redesign before results. Even passing it does not remove missingness bias. A tiny valid sample cannot be relabeled as the six-year study. Feature-specific gap policies are later preregistered work.

## 7. Procurement/open gates

Recommend Databento historical PAYG for this archive, conditional on exact quote, local retention/derived-data rights and delivered per-contract coverage; FirstRate individual MES CSVs are the principal alternative. IBKR remains the broker and can be a future authorized recent-data check; its expired-futures limit cannot supply the 2022 pilot or full archive now. No purchase is approved. [Provider evidence and quote inputs](PROVIDER_COMPARISON.md).

Open items before real-data admission: exact quote/taxes/credits (not assumed), written retention after termination, actual 25-contract definitions/coverage, machine-readable historical cash/CME calendars including ad-hoc closures, provider revision/aggregation details, valid precision/ID mapping, and measured delivery/fill evidence for any later execution claim. M2a closes by specifying these gates; M2b must not mark them verified until supplied artifacts and tests prove them.
