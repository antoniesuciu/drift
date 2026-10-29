# EXP-001 — MES intraday time-series momentum adaptation

**State:** Research design only; not executed. Rule-based implementation M3; validation M5. No return, Sharpe, win rate or profitability is claimed. See [synthesis](../../docs/RESEARCH_SYNTHESIS.md) for paper evidence and distinctions from replication.

## Hypothesis and rule

Hypothesis: alignment of early-session and pre-close momentum may predict an executable final-half-hour MES return after costs. Null: this alignment offers no robust positive net expectancy or useful advantage over controls on unseen data. The rule is a proposed adaptation; an academic finding on another instrument/sample does not verify it.

For an eligible full US cash session, use the same actual expiring MES contract for all prices:

`r_early = P(10:00 ET) / P(previous full cash-session close at 16:00 ET) - 1`

`r_preclose = P(15:30 ET) / P(15:00 ET) - 1`

Long if both strictly positive, short if both strictly negative; otherwise NO_TRADE. Maximum one entry per eligible session. A zero return abstains. Prices are positive, validated completed-bar endpoints, not bar-start labels used as close observations. On holidays/early closes, missing endpoints, stale data, unknown mapping or a contract roll between endpoints, abstain and record why. Skip sessions following an early-close session for this first frozen variant, so the prior endpoint remains an unambiguous full-session close.

The first return includes overnight information. Do not replace it with 09:30→10:00 without registering a separate experiment. Exact paper formulas, fitted regression, sample and ETF/futures differences belong in a replication protocol before any replication claim.

## Decision and execution timing

Use UTC internally and `America/New_York` plus a versioned cash calendar for windows. For minute bars, `P(15:30)` is the close of the bar ending 15:30, available only after that bar completes plus declared feed/processing delay. Databento raw OHLCV timestamps label interval start; normalize explicitly. The [provider document](../../docs/COSTS_AND_PROVIDERS.md) and [requirements](../../REQUIREMENTS.md) govern timestamp validation.

Generate the proposal after all inputs are available. Enter at the first eligible subsequent executable quote/trade, with a declared latency, never retrospectively at the signal-generating close. For OHLCV-only replay, use a conservative next-bar convention and document its optimism/uncertainty; equal event timestamps require explicit event ordering, not an assumption of instantaneous fills.

Exit target is by the 16:00 ET cash close, using a preregistered scheduled liquidation lead time/latency that does not depend on observing the future 16:00 closing price. Declare fill eligibility at the cutoff and what happens to unfilled/partial residuals; log cutoff failure, carry remaining exposure explicitly in PnL/risk and flag the run for review. Never invent a fill to enforce a flat position. No new entry if insufficient time remains under this policy. Intended holding period is approximately 30 minutes and can be shorter due to entry latency/exit lead time.

## Freeze before results

M2 must establish accessible contract-level coverage. Before running M3 on real data, record exact dates/contracts, raw/curated hashes, trading calendar/version, price endpoints, roll policy, minimum coverage, delivery/processing latency, sizing, exit/cutoff behavior, fee tier, spread/slippage scenarios, dataset rights and the code/config versions. These are unresolved inputs, not defaults hidden in code.

Use one MES contract as an arithmetic research baseline only after the configured synthetic risk budget permits it; a minimum tradable size can exceed the eventual capital budget. Positions must not be scaled from day margin. MES point/tick math and all fees follow the [cost model](../../docs/COSTS_AND_PROVIDERS.md). Avoid adding spread again if the fill prices already use bid/ask. Report commissions/fees and price impact separately.

Freeze chronological development, validation and untouched final holdout dates before viewing outcomes. Track every attempted variant; changed windows/costs/thresholds create a new trial ID. Walk-forward fitting applies to any later ML filter, not the fixed rule itself. Purge overlapping labels where relevant. Preserve rejected ideas and reasons.

## Controls, metrics and decision

Compare no-trade, simple unconditional same-window direction, early-sign-only and preclose-sign-only baselines. A seeded randomized-direction control can test conditional signal value while matching trading dates/holding windows; use dependence-aware uncertainty and document its limits. These are controls, not extra hidden candidate searches. Include gross/net PnL and returns with capital definition, fees, turnover, trade count, drawdown, win/loss distribution, regime/roll slices and cost/latency sensitivity. Report coverage and skipped-session counts alongside performance.

Before final holdout access, write numeric candidate promotion criteria tied to actual costs, sample adequacy and risk tolerance, with an uncertainty method appropriate to serial dependence. Research completion requires a reproducible go/modify/reject verdict, not a positive Sharpe. A modified strategy returns to development with a new trial record; repeated reuse of the same final holdout must be disclosed and cannot remain called untouched.

## Required test cases

Long/short/zero/disagreement and exact endpoint availability; duplicate/missing/late bars; UTC/ET DST and holidays/early closes; prior early-close exclusion; same-contract/roll mapping; proposal expiry/deduplication; one-entry limit; next-event fill and nonzero latency; cutoff/partial fills; explicit commissions/spread/slippage; long/short multiplier PnL; over-budget rejection and halt. No broker connection or order submission is needed to test this design.
