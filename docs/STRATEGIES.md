# Rule strategies

Specification of the deterministic RULE-family models in `src/quantlab/strategies/rule/`: seven statistical and candlestick strategies that share the proposal contract ([architecture](ARCHITECTURE.md#proposal-contract)), one session calendar and the shared backtest sizing, risk and exit layer. Requirements are [REQ-STRAT-001–016](../REQUIREMENTS.md); the roadmap owns sequencing and gate status. **These are hypotheses to test, not claims.** The software is verified on synthetic data only: no real data, no measured return, and every historical gate remains pending. The research reports are preserved evidence inputs ([archive](archive/research/README.md)), so each model says how much of it they define. Thresholds in this document are version-tagged research choices to freeze per experiment, not universal definitions.

## Statistical rules (`rule/statistical/`)

### Shared conventions

- **Inputs:** completed 1-minute candles, each with its own availability time. A rule sees only candles already pushed, so a decision is made when the candle that completes its inputs becomes available (`generated_at = data_asof = candle.available`). Windowed readings (VWAP, Bollinger, reversal buckets, trend) never span sessions or a missing minute: a gap suppresses the signal rather than being filled. ORB needs a complete opening range and ITSM every minute up to its decision.
- **Clock:** all windows are New York wall-clock times from the versioned session calendar. The research quotes CET windows (for example 17:30–20:00 CET); the lab anchors to 11:30–14:00 ET, which matches except in the few weeks when US and EU daylight saving differ.
- **Output:** one shared `Proposal` (LONG, SHORT or NO_TRADE with reason codes). A rule never sizes, orders or exits by itself.
- **Sizing, risk, exit and fills:** the shared backtest layer applies fixed-quantity or target-notional sizing, the deterministic risk limits (which have no defaults), the exit policy (time horizon, session flatten 120 seconds before the close, optional ticks/percent stops, opposite-signal exit where stated) and the fill convention of REQ-BACKTEST-003.
- **Defaults** are version-tagged placeholders so a configuration is complete; they are not tuned and carry no evidence. The resolved configuration and its hash are recorded in every report.

### ITSM (EXP-001) — `itsm.py`

Specified in [EXP-001](../experiments/exp001_itsm/README.md): `r_early = P(10:00) / split-neutral previous close − 1`, `r_preclose = P(15:30) / P(15:00) − 1`; both positive proposes LONG, both negative SHORT (if allowed), otherwise NO_TRADE. One decision per full session at the 15:30 candle; abstains on early closes, an early-closing previous session, missing endpoints or gaps. Exit: session flatten (the position is held about 28 minutes by default). Parameters: endpoint clocks, `allow_short`, `entry_valid_seconds`, `splits` (date and share ratio).

### Opening range breakout — `orb.py`

| Item | Definition |
|---|---|
| Source | Report 02 (hypothesis 1: first 15 or 30 minutes, relative volume filter, 15–60 minute horizon, active window 09:30–11:00 ET) and report 03 (range of 5, 15 or 30 minutes; VWAP and volume filters; prior true range below the 20-day ATR). Report 03 also records unconditional futures ORB as unsupported, so the filters matter. |
| Range | High and low of the first `range_minutes` ∈ {5, 15, 30} from 09:30. Incomplete range: abstain (`range_incomplete`). |
| Signal | In the window ending at `entry_cutoff`, the first completed candle whose close is strictly above the range high (LONG) or below the low (SHORT) and that passes every enabled filter. One proposal per session; if none qualifies, NO_TRADE at the cutoff candle with the accumulated reasons (`no_breakout`, `direction_disabled`, `filter_failed:*`, `filter_warmup:*`). |
| Filters (all off by default) | `rvol_min`: opening-range volume ÷ mean over the prior `rvol_lookback` sessions. `vwap_alignment`: close beyond the session VWAP on the trade side. `breakout_volume_multiple`: breakout candle volume ≥ multiple × the range's mean bar volume. `prior_tr_below_atr`: yesterday's true range < ATR over n ended, complete sessions. |
| Exit | Time horizon from the fill (`horizon_seconds`, default 1800) or the session flatten; no opposite-signal exit. |
| Defaults | `range_minutes` 15, `entry_cutoff` 11:00, both directions, `horizon_seconds` 1800, `entry_valid_seconds` 300. |
| Not implemented | Catalyst ("stocks in play") selection and event-free-day filters (cross-sectional and calendar data); volatility-scaled triple-barrier exits and meta-labeling (ML); the 1R/10R and stepped trailing stops of the cited studies (they need a per-trade stop contract that shared risk owns). |

### Mean reversion — `vwap_reversion.py`, `bollinger_reversion.py`, shared `fade.py`

| Item | Definition |
|---|---|
| Source | Report 02 (hypothesis 4: 2.0-sigma extensions from session VWAP in a low-volatility midday window revert over 15–30 minutes; "VWAP / Bollinger Band mean reversion on MES"). Report 03 records unconditional intraday fading as a loser on trending instruments, so regime gating is the research's own condition. |
| VWAP reading | `z = (close − VWAP) / σ`, where VWAP is the volume-weighted mean of typical price `(high + low + close) / 3` since the open and σ its volume-weighted standard deviation. Undefined (no signal) with no volume, zero dispersion, fewer than `min_bars` candles, or a missing minute since the open. |
| Bollinger reading | On completed `timeframe`-minute candles: middle = mean of the last `period` closes of the same session (current close included), σ = population standard deviation of those closes, `z = (close − middle) / σ`. A new session or a missing bucket restarts the window. |
| Signal | Edge-triggered: a reading that newly reaches `z ≥ k` is faded SHORT and one that newly reaches `z ≤ −k` is faded LONG, only when the decision candle ends inside `[window_start, window_end]`. A reading that stays outside the band does not repeat; an undefined reading clears the state. |
| Exit | Time horizon from the fill (default 1200 seconds) or the session flatten; no opposite-signal exit. |
| Defaults | `sigma_multiple` 2.0, window 11:30–14:00 ET, `horizon_seconds` 1200; VWAP `min_bars` 30; Bollinger `timeframe` 5, `period` 20. |
| Not implemented | Regime gates: no scheduled macro release (no calendar data) and opening-range width against a percentile of 20-day ATR (ambiguous in the source). Gap-fill variants and exit at the VWAP touch. |

### Short-term reversal — `reversal.py`

Source: [project audit appendix D](archive/audit/PROJECT_AUDIT.md) (trailing 15-minute return reversal, next-available entry, 15-minute exit, long/flat control; literature: Nagel, Heston/Korajczyk/Sadka). On each completed session-aligned bucket of `timeframe` ∈ {5, 15, 30, 60} minutes, `move = close/open − 1`; a negative move proposes LONG and a positive move SHORT when `|move| × 10,000 ≥ min_abs_return_bps`; a zero move or one below the threshold is no signal. Buckets are non-overlapping, so successive signals are independent. Exit: time horizon (default 900 seconds) or the session flatten. `allow_short = false` is the audit's long/flat control. Defaults: `timeframe` 15, threshold 0, `horizon_seconds` 900.

### Trend following — `trend.py`

The research names a "60-minute trend-following strategy" without a rule, so this is the lab's own standard definition. On completed `timeframe`-minute candles of one session: `fast` = mean of the last `fast` closes, `slow` = mean of the last `slow` closes. A fresh cross of fast above slow (previously `fast ≤ slow`) proposes LONG; fast below slow (previously `fast ≥ slow`) proposes SHORT. Evaluation needs `slow + 1` same-session closes. The position leaves on the opposite cross (the shared opposite-signal exit, which does not reverse in the same step; a cross toward a disabled direction proposes FLAT, so it still exits) or at the session flatten. Defaults: `timeframe` 5, `fast` 5, `slow` 20.

### Future work: relative strength and other families

- **Relative strength/weakness** (report 02, hypothesis 3: abnormal 15-minute return and volume against the S&P 500 or Nasdaq-100 over the first hour, continuing 30–60 minutes) needs benchmark data, a statistical significance definition and a multi-instrument agent contract. It is not implemented (REQ-STRAT-016).
- **Statistical arbitrage and pairs** need synchronized multi-leg data and two-leg costs. **Volatility breakout** (Keltner/ATR expansion after compression) lacks a compression definition. Both remain deferred.
- **ML filters and meta-labeling** named in the reports belong to M4.

## Candlestick patterns (`rule/candlestick/`)

Candlestick agents belong to the RULE family; the detector is a deterministic, reusable component and the trading policy is separate. M3a (ITSM) precedes M3b (candlesticks) as evidence: no candlestick historical result before M3a signoff.

### Detection catalogue and configuration

For each valid completed candle, define body `B=abs(close-open)`, range `R=high-low`, upper wick `U=high-max(open,close)` and lower wick `D=min(open,close)-low`. Use exact prices/tick-aware comparisons. Configuration must specify all body/range and wick/body thresholds, comparison equality/tolerance, lookback lengths, gap requirements and contextual rules. Ratios need valid denominators: mark zero-range candles degenerate and withhold ratio-dependent detections rather than divide by zero or assign an automatic Doji. For zero body but positive range, body/range remains valid for Doji; undefined wick/body ratios cannot authorize other detections. Reject invalid OHLC, unsupported parameters and missing required history with explicit reasons.

| Detection ID | Candles | Predicate that the frozen configuration must make exact |
|---|---|---|
| `bullish_engulfing` | 2 | First body bearish, second bullish; second real body contains the first body. Declare strict versus inclusive edges; wicks are not the engulfed body. |
| `bearish_engulfing` | 2 | Mirror of bullish engulfing: bullish then bearish, second real body contains the first. |
| `hammer` | 1 | Small body, sufficiently long lower wick and bounded upper wick; configure minimum range/body and wick ratios and any candle-color condition. Prior trend is a separate optional confirmation. |
| `shooting_star` | 1 | Small body, sufficiently long upper wick and bounded lower wick; configure the mirrored thresholds and any color condition. |
| `morning_star` | 3 | Long bearish body, small middle body, then bullish body closing a configured fraction into the first body. Freeze long/small-body, penetration and gap rules. |
| `evening_star` | 3 | Mirror of Morning Star, finishing with a bearish body penetrating the first bullish body. |
| `doji` | 1 | Positive range and body/range at or below the configured small-body threshold. A neutral observation; context/entry policy must supply any directional hypothesis. |
| `three_white_soldiers` | 3 | Three bullish bodies with successively higher closes; each later open within the previous body. Freeze body-length and upper-wick bounds and edge inclusivity. |
| `three_black_crows` | 3 | Three bearish bodies with successively lower closes; each later open within the previous body. Freeze body-length and lower-wick bounds. |
| `inside_bar` | 2 | Second high/low contained within the first range, with strict/inclusive edges explicitly configured. Neutral until a registered directional/confirmation rule is satisfied. |

Gap requirements are explicit, including a no-gap-required variant for continuous trading sessions; never silently switch definitions by instrument. Define tolerances in ticks or dimensionless ratios, not an unexplained price constant. Configuration validation must reject impossible ratios, nonpositive lookbacks and undefined comparison modes. Threshold defaults, if later supplied, are versioned research choices and must be frozen before results.

Each instance configures instrument ID(s), one or more timeframes from **1m, 5m, 15m, 30m, 1h**, enabled patterns, detector/parameter versions, optional confirmations and entry/exit/protection policy. Pattern detection uses supplied instrument metadata; it must not hard-code MES prices, tick sizes, currency or multiplier. Actual market admission still requires data, calendar, cost and risk evidence; configurable interfaces do not imply that today's synthetic MES runtime already supports NVDA. NVDA/Alpaca is the initial real-data plan; future instruments reuse detector interfaces after their own admission. Use one admitted instrument/agent at a time in M3; independent configurations can be evaluated sequentially.

### Completed candles, aggregation and confirmations

A detection can use only validated candles whose **end and availability times are <= the decision clock**. A candle's start label is never its completion time. Preserve source interval, actual instrument/expiry, aggregation clock, provenance, versioned session/calendar, completion and measured or modeled availability. A multi-candle pattern has the maximum availability of all its required inputs; include any additional trend/filter history in the proposal's input cutoff.

When deriving higher timeframes from available base bars, freeze the bucket origin/timezone, session alignment, boundary inclusion and break/partial-bucket policy. Aggregate only the same actual instrument/contract in chronological order, with OHLC from constituent bars and summed volume. Publish a bucket only after its declared end and all required constituent observations are available, plus any declared aggregation delay. Define derived availability at least as `max(bucket_end + aggregation_delay, constituent availability times)`. Missing/unknown source intervals or truncated end-of-session buckets remain not ready under the initial full-bucket policy; do not pad prices or publish a short bar as a full hour. Scheduled closures must be calendar-classified rather than treated as absent trades.

Explicitly configure whether a multi-candle window may span sessions and how legitimate session gaps are treated; unresolved missing intervals cannot count as consecutive candles. Never detect across an expiry/roll by stitching old/new futures prices. For multiple timeframes, the higher-timeframe candle must also be completed and available; using its evolving high/low/close would leak future information. Later bars, outcomes or retrospective revisions must not rewrite earlier observations or proposals; corrections create a new dataset/run version.

All confirmation filters are **optional to enable**; an enabled filter is required to pass for that configuration. Freeze their definitions and parameters:

| Filter | Required causal specification |
|---|---|
| Trend direction | Trailing estimator/window and allowed direction or reversal context; fit/adapt only on information available at the decision. |
| Support/resistance | Trailing level construction, lookback, distance/tolerance and level availability. A pivot requiring later candles becomes known only after those confirming candles are available; never backdate it. |
| Volume | Required units/field, trailing baseline, comparison threshold and lookback. Missing volume is unavailable, not invented; avoid full-session volume normalization before the session ends. |
| Volatility | Trailing estimator/window, allowed range or threshold, warmup and units; no centered or future-looking estimate. |

Disabled filters add no hidden condition. Failed, missing, stale or insufficient-history enabled filters yield `NO_TRADE` with a reason and remain counted in coverage. Pattern morphology is not a calibrated probability. Multiple simultaneous detections are retained as observations; opposite directional candidates cause abstention under the initial conservative policy. Any alternative precedence or combination rule must be explicit, versioned and tested; detection iteration order cannot decide trades.

### Shared signals and trading policy

The detector is a deterministic reusable component: validated completed candles plus frozen configuration produce pattern observations and shape attributes, with no orders, portfolio state or fitted model. A small observation records detection ID/version, instrument, timeframe, candle-span end, availability, source/input references, parameter hash, validity/reason and useful body/wick/range attributes. This is data provenance, not a fourth agent family or a separate messaging service. Represent absence as no detection and distinguish it from invalid/not-ready input.

The candlestick policy consumes those observations and causal confirmation snapshots, then emits the **existing proposal schema**, without a parallel signal/order interface:

| Existing fields | Candlestick interpretation |
|---|---|
| `family`, `agent_id`, `strategy_id` | `RULE`, configured instance identity and registered candlestick variant/trial. |
| `instrument_id`, `horizon_seconds`, `valid_until_utc` | Actual admitted instrument, configured holding horizon and finite expiry; timeframe alone does not determine holding period. |
| `generated_at_utc`, `data_asof_utc` | Decision creation and maximum input availability, including filters and higher-timeframe context; retain the common clock inequalities. |
| `rule_or_model_version`, `input_refs` | Detector, parameters, aggregation/calendar, confirmations, policy and dataset/decision-artifact references sufficient to reproduce the proposal. |
| `intent`, `rationale` | Existing LONG, SHORT, FLAT or NO_TRADE with pattern/confirmation/exit reason and evidence references. Doji/Inside Bar alone do not select LONG/SHORT. |
| `proposal_id`, optional score/quantity fields | Idempotent occurrence/intent identity under the common run/agent policy; repeated input cannot cause a second entry. A shape score is labeled as such, not win probability; quantity hints remain non-binding. |

Use the existing `NO_TRADE` and allocation-specific `FLAT` meanings; an abstention neither cancels orders nor closes another agent's position. Keep per-timeframe occurrence, duplicate/repeated detections, pending entries, pyramiding/maximum-entry and opposing-signal behavior explicit in the policy. M3 does not enable concurrent agents or compare uncalibrated cross-agent scores.

Every trading variant freezes:

- **Entry:** directional mapping/context for each enabled pattern, next eligible executable event or completed-candle breakout/confirmation rule, order constraints, expiry, latency and entry/session limits. A pattern close, or next bar's open occurring before its availability, cannot supply a retrospective fill. An intrabar execution trigger is distinct from a completed-candle detection.
- **Exit:** holding/time or session cutoff, opposite-signal behavior, unfilled/partial order and residual-exposure handling. A future candle's close cannot trigger an earlier liquidation.
- **Stop-loss and take-profit:** explicit enabled/disabled settings, fixed ticks/percent or a declared causal volatility-based distance, reference price, tick rounding, update/trailing policy and validity. Reject nonpositive/wrong-side levels or inconsistent units; no undocumented protection defaults.

The referenced versioned policy/decision artifact carries these proposed constraints. Shared portfolio/risk owns final sizing, permitted levels and authorized intents; execution owns order lifecycle. Agents do not submit stops or bracket orders directly. The historical fill model must account for gaps, slippage, commissions/exchange/regulatory fees, spread without double-counting, and OHLC path uncertainty. If stop and target are both touched within a bar, use a frozen conservative convention or resolve with separately justified finer evidence; never select the profitable ordering after seeing the result. Stop levels do not guarantee fills at that price.

### Reuse by ML and evaluation gates

Separate recognition/shape calculation from confirmation, directional entry/exit policy and the common proposal adapter. Reuse the same detector version and availability rules for later ML features: pattern flags, shape ratios and recency may be causal features, while future returns are separate labels. Feature records retain instrument/timeframe, input cutoff, version and source references. No model training, feature selection or scaling on the full history is implied; M4/M5 training-fold fitting and overlap purging/embargo still apply. Backfilled centered/pivot confirmations cannot become earlier ML features.

Prefer existing validated data/Nautilus facilities and small functions/components when M3b is authorized. No new TA dependency, plugin framework, registry service or source-code skeleton is required by this plan. Today's data cap, M2 rights/admission gates and EXP-001 implementation priority remain unchanged.

| Gate | Measurable future evidence |
|---|---|
| CANDLE-001 — catalogue | All **10 detection IDs** have hand-specified positive, negative and exact-boundary fixtures, including mirrored directions, equality/gap variants, insufficient history, zero range and invalid OHLC. Deterministic expected detections/attributes match at declared tick precision. |
| CANDLE-002 — configuration | All five timeframes are accepted and unsupported ones rejected; two synthetic instrument specifications with different ticks/multipliers prove metadata-driven behavior and no cross-instrument state contamination. Registering a fixture is not admission of a real market. Invalid thresholds, instrument/config mismatches and missing required fields fail explicitly. |
| CANDLE-003 — causal aggregation | Hand-calculated OHLCV/time/availability for each timeframe match; tests cover exact boundaries, delayed last component, partial buckets, session breaks, DST, warmup, out-of-order/duplicate/missing bars and futures rolls. Before availability: no usable detection; after availability: exactly the expected result. |
| CANDLE-004 — no future influence | Hold pre-cutoff candle inputs/configuration fixed, then alter/append/remove future candles, future higher-timeframe components and later outcomes: earlier detection values, validity/reasons, proposal intents and decision/availability times remain identical. Across rebuilt immutable datasets, audit changed run/checksum lineage separately from those logical outputs; preserve original emitted history. Later-confirmed pivots first appear at their actual confirmation availability. Historical revisions require a new run/version. |
| CANDLE-005 — confirmations | Each of four filters passes/fails independently and in configured combinations. Disabled filters do not change results; missing/stale/warmup-failed enabled filters abstain with stable reasons. Opposing patterns abstain; neutral patterns cannot create direction without their registered rule. |
| CANDLE-006 — common proposals | Each configured pattern policy produces valid shared RULE proposals or reasoned abstentions. Validate clock/expiry, source/config lineage, duplicate detection/delivery, FLAT attribution and risk rejections; no broker path is available to the detector/agent. Same fixed inputs reproduce proposals. |
| CANDLE-007 — trading and costs | Exercise configured entry/exit/stop/target policies with hand-calculated long/short trades, tick/currency math, fees, spread/slippage, latency, gaps, same-bar stop/target ambiguity and partial/unfilled/residual cases. No fill precedes the relevant information or bypasses shared risk. |
| CANDLE-008 — historical research | After M3a signoff, run at least one preregistered candlestick variant end-to-end on admitted historical data through the native engine, with gross/net costs, coverage, exclusions, trade count, drawdown and cost/latency sensitivity; retain every attempted configuration and negative result. Only evaluated variants may claim evidence; one successful run does not validate every pattern/filter/timeframe combination. |
| CANDLE-009 — before paper | Each proposed paper variant needs frozen chronological out-of-sample/walk-forward evaluation and an M5 go/modify/reject verdict against preregistered numeric promotion criteria, simple/no-trade controls, sample adequacy and uncertainty. Keep final holdout untouched until the frozen protocol permits access. Only an approved verdict plus M6 entitlements/risk/operational gates and explicit user authorization permits paper trading; positive in-sample performance is insufficient. |
| CANDLE-010 — ML reuse | On identical candle snapshots/configuration, ML feature observations and rule-policy inputs have identical detection values, versions and cutoffs. Tests reject future labels/inputs and insufficient history; M4 fitted transforms use training folds only. No trading policy, broker state or future outcome is needed by the detector. |

M3b completion requires CANDLE-001–008 and the reusable detector-side evidence of CANDLE-010. M4 verifies fitted-feature use; M5/M6 own CANDLE-009 and paper promotion. A reproducible negative research verdict can complete the research work while preventing paper activation. All gates above are **planned and pending**, not results of this documentation task.
