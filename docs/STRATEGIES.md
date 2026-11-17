# Rule strategies

Specification of the deterministic RULE-family models in `src/drift/strategies/rule/`: six statistical strategies that share the proposal contract ([architecture](ARCHITECTURE.md#proposal-contract)), one session calendar and the shared backtest sizing, risk and exit layer. Requirements are [REQ-STRAT-001–016](../REQUIREMENTS.md); the roadmap owns sequencing and gate status. **These are hypotheses to test, not claims.** All six policies are verified on synthetic data; only ITSM has additionally run on the small [real SIP feasibility slice](data/ALPACA_PILOT.md), producing abstentions. No strategy has historical acceptance or profitability evidence. The research reports are preserved evidence inputs ([archive](archive/research/README.md)), so each model says how much of it they define. Thresholds in this document are version-tagged research choices to freeze per experiment, not universal definitions.

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
