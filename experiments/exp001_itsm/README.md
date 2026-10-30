# EXP-001 — NVDA intraday momentum adaptation

**Protocol: EXP-001-NVDA-v1, 2026-10-30. State: protocol frozen; the rule and a synthetic-data backtest are implemented (2026-10-30), with no real data and no measured returns.** Initial NVDA/Alpaca/IBKR scope is confirmed by the user. This replaces the unexecuted MES design as the active experiment; historical MES code/tests and specifications remain regression evidence. The split is preserved, not reselected from observed results. [Requirements](../../REQUIREMENTS.md), [NVDA data plan](../../docs/data/NVDA_DATA_PLAN.md) and [roadmap](../../docs/ROADMAP.md) govern admission and sequencing.

## Hypothesis and reusable policy

Hypothesis: agreement of overnight-plus-early momentum and pre-close momentum predicts NVDA's final-half-hour return after realistic execution costs. Null: it has no robust positive net expectancy or useful advantage over controls on unseen data. Academic SPY findings and earlier MES planning do not establish NVDA alpha or a paper replication.

The policy receives available observations and effective instrument/action metadata; it does not create provider or broker clients. Instrument, provider, fee policy, allowed directions and execution adapter are independently configured. NVDA is the sole real initial instrument, not a constant embedded in the reusable sign-agreement calculation.

On a full eligible US cash session:

```text
r_early = P(10:00) / split_neutral_previous_close − 1
r_preclose = P(15:30) / P(15:00) − 1

both strictly positive → LONG proposal
both strictly negative → SHORT proposal, subject to the frozen direction/borrow policy
zero, disagreement or unavailable inputs → NO_TRADE with reason
```

Use the immediately preceding cash session; if it closes early, abstain rather than skip back to a convenient earlier full session. Current early-close/closed sessions also abstain. Maximum one entry per eligible session. Unknown instrument mapping, required split actions, missing/stale endpoints or earlier unknown input gaps abstain and stay in coverage.

All signal endpoints are closes of the completed minute **ending** at the stated New York clock. Prior close is that minute's close ending 16:00, not an assumed official auction price. The early return includes overnight information. Record this proxy and its difference from any paper's official close methodology.

Across a split, express the prior raw close on the current share basis using the known effective factor; for a 4:1 split, divide the old close by four. Keep executable prices/share quantities raw. The baseline is split-neutral price return, with cash dividends left in the overnight price return; a total-return variant needs its own trial. Missing action evidence cannot become a false momentum signal.

Historical short scenarios must declare assumed borrow availability/rates and are hypothetical until account evidence exists. Freeze allowed directions before results; a long-only policy is a named variant, not silent removal of losing shorts. Shared portfolio/risk owns final quantities and permission checks; proposals are not orders.

## Decision and execution time

Use UTC internally, `America/New_York` and a versioned cash calendar. Alpaca minute labels are starts: the 15:29 bar completes at 15:30 and becomes usable only after declared availability. Baseline 1-second and adverse 60-second modeled delays are research assumptions, not measured service guarantees.

Generate after all required observations/actions are available. Enter at the first eligible subsequent executable event. A signal close or next-bar open that already occurred before availability cannot be a retrospective fill. OHLCV-only replay needs a frozen conservative fill convention, explicit event ordering and disclosed uncertainty.

Target liquidation by the 16:00 cash close through a scheduled lead time and latency frozen in advance; do not observe the final close to choose an earlier exit. Record partial/unfilled/residual exposure and any missed cutoff in PnL/risk. Never invent a fill to guarantee flatness. Intended hold is approximately 30 minutes, shortened by entry latency/exit lead.

## Freeze before results

- Dataset `NVDA-SIP-DATA-v1`: study 2020-01-02–2025-12-31, prior 2019-12-31 context and declared warmup. Development 2020–2022; validation 2023; final holdout 2024–2025. The audit's alternative split was not adopted.
- Rights/access, feed, raw hashes, action/mapping/calendar versions, coverage/exclusions and historical revision/availability limitations.
- Policy/config/version, allowed directions and assumed short availability; whole-share quantities, numeric historical risk budget, entry/exit/cutoff handling and event-order convention.
- Dated commissions/minimums, route/regulatory/clearing charges, raw tick/share math, spread/slippage, FX and borrow/financing assumptions; zero/base/stressed scenarios and sample-adequacy/promotion criteria.
- Every trial and failed/rejected variant. Retuning creates a new trial/protocol, not reuse of an untouched holdout claim.

No capital, fee tier, borrow, numeric risk limit or profitable configuration is silently supplied by this document. M2 admission precedes M3 execution; user authorization for requirements does not start either implementation or acquisition.

## Controls, metrics and acceptance

Compare no-trade, unconditional same-window direction, early-sign-only and preclose-sign-only controls. A seeded randomized-direction control should match eligible dates/windows and disclose dependence. Report gross/net PnL with capital definition, fees, exposure/turnover, trade counts, drawdown, exclusions, action/calendar slices and cost/delay sensitivity; use dependence-aware uncertainty rather than treating minute bars as independent trades.

M3 needs reproducible proposals and raw-share PnL through native simulation with hand-calculated long/short, action, fee/minimum, timing, missing/revised data, early-close, duplicate, partial-fill, cutoff and risk-rejection cases. The policy must consume the shared interface with no Alpaca/IBKR import. A second synthetic instrument and another policy fixture verify extension without admitting another real market.

M5 independently evaluates frozen out-of-sample evidence before any M6 paper proposal; rule-only validation does not require ML implementation. Null/negative research can complete the experiment and block promotion. M3b candlestick research follows the initial baseline; crypto and ML/LLM model selection remain deferred. No account connection or order submission is required to test this protocol.
