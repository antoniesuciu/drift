# Providers, compatibility and cost discipline

Active scope revised **2026-10-30**: NVDA ordinary shares, Alpaca historical SIP data, Alpaca paper execution (D-032 supersedes IBKR). [D-026–028](DECISIONS.md) records the user decision; [NVDA data plan](data/NVDA_DATA_PLAN.md) owns requests and admission gates. The [audit](archive/audit/PROJECT_AUDIT.md) preserves wider dated comparisons; crypto and MES procurement are outside current work.

## Independent roles

| Role | Current choice | Evidence still required |
| --- | --- | --- |
| Historical provider/feed | Alpaca stock bars, explicit SIP, initial NVDA minute data | Applicable account/region/data-use rights, actual coverage, adjustments, pagination and historical availability assumptions |
| Instrument | NVDA ordinary shares, USD | Effective identity/mapping, price/quantity increments, actions, sessions and raw/adjusted unit consistency |
| Execution broker | Alpaca paper, fixed paper REST host | ACTIVE/USD account and NVDA tradability verified; usable in-session IEX quotes and actual paper fills/reconciliation pending ([evidence](PAPER_EXECUTION.md)) |
| Simulation/storage | Pinned NautilusTrader 1.231.0 / native Parquet | Synthetic compatibility and the four-session NVDA native catalog/ITSM feasibility replay are verified; full admission remains pending |
| Analytics | Existing Python tools; optional DuckDB/dataframe tools when useful | No new dependency or service needed for this documentation task |
| Other markets/providers/brokers | Extension interfaces preserved; actual admission deferred | Concrete need, capability/rights/calendar/cost/risk evidence and a separate authorized task |

Select these roles independently through small interfaces. Provider HTTP details belong to a data adapter, instrument specifications to metadata, strategy policy to its module, and broker contract/order handling to an execution adapter. No broker client is created by an agent. [Architecture](ARCHITECTURE.md#extension-interfaces) defines extension behavior and [REQ-ARCH-002](../REQUIREMENTS.md) its measurable acceptance.

## Alpaca: historical access is distinct from live data

Official [plans](https://docs.alpaca.markets/us/docs/about-market-data-api), [FAQ](https://docs.alpaca.markets/us/docs/market-data-faq) and [bars reference](https://docs.alpaca.markets/us/reference/stockbars), rechecked **2026-10-30**, document free historical SIP queries older than 15 minutes, history advertised since 2016 and Basic's 200 historical requests/minute. Bars have up to 10,000 total records/page and require complete pagination. Free live IEX is not consolidated SIP. The [authorized four-session NVDA pilot](data/ALPACA_PILOT.md) now verifies historical SIP access for that slice. It does not prove complete NVDA history, account/region classification, live SIP access or unrestricted archival rights.

Use explicit feed, raw adjustment, mapping date, request bounds and modeled availability; preserve raw response hashes and revisions. Keep split-neutral research views separate from raw share execution. The active data plan records admission tests, rights uncertainty and source links. Do not assume `asof` supplies a point-in-time corporate-action vintage or silently replace SIP with IEX.

The owner separately selected and authorized **Alpaca paper** (D-032). A stdlib REST adapter and bounded ITSM runner use the shared durable risk gate, with no SDK dependency. Current operational IEX data remains distinct from historical SIP research; no live SIP subscription or live-money endpoint is enabled. See [paper commands, verified reads and limitations](PAPER_EXECUTION.md).

## Framework compatibility and actual implementation

[M1 evidence](M1_FOUNDATION.md) verifies Python 3.12 / NautilusTrader 1.231.0, locked dependencies, real engine timing and IB adapter imports. [M2b.1](data/PIPELINE.md) verifies native DBN/catalog/provenance and order-free synthetic MES replay. This work remains valid regression evidence; it does not prove real NVDA data support, fee/fill behavior or authenticated IBKR compatibility.

Use release-tagged documentation matching the installed tuple; moving 2.x examples are not evidence for 1.231.0. Preserve the current native catalog and causal snapshots. Add only the equity/source metadata and adapters the NVDA task needs, with interfaces tested independently of strategy/risk. No migration, dependency install, broker app or empty agent framework is part of this scope update.

## NVDA execution costs and units

For whole-share research quantity `q`, direction `d` in `{−1,+1}` and raw USD/share fills:

```text
notional USD = q × raw price × equity multiplier (1)
gross fill PnL USD = d × q × (exit_fill − entry_fill)
net trading PnL = gross fill PnL − commissions − venue/clearing/regulatory fees
                 − applicable borrow/financing/FX/other charges
```

Corporate-action transforms must preserve share/value math. Use raw prices/shares to apply effective tick rules and per-share commissions. Split-adjusted feature prices are not executable fill prices. Fractional quantities need separate broker/increment validation; the first baseline uses configured whole-share quantities.

The earlier **IBKR research cost reference, not the active paper adapter**, uses the [IBIE US stock schedule](https://www.interactivebrokers.ie/en/pricing/commissions-stocks.php), rechecked **2026-10-30**, which lists lowest-volume Tiered **$0.0035/share, $0.35/order minimum** and Fixed **$0.005/share, $1/order minimum**. These are commission inputs, not total round-trip costs. Venue, clearing, regulatory charges, route, rounding and account terms matter; the overview/detailed Fixed treatment differs, as recorded in the audit. Preserve dated source snapshots/configuration rather than backdating today's schedule into 2020–2025.

Freeze zero/base/stressed cost scenarios before results, including commissions/minimums, spread, slippage, latency, partial/unfilled orders and USD/EUR valuation. If buys fill at ask and sells at bid, spread is already reflected; do not subtract it twice. Bar-only fills cannot establish queue position or live execution quality. Short research needs explicit assumed borrow availability/rates; actual short activation requires broker permission and available inventory. No universal zero intraday borrow, fee tier or account margin regime is assumed.

Budget FX on actual conversions, not every order solely because the account base currency is EUR. Separate historical-data cost, optional live subscriptions, transfers and infrastructure from per-trade PnL. Free IEX is selected for the separate Alpaca paper operational trial; usable in-session quotes still need verification. For any future IBKR reconsideration, [IBKR market-data pricing](https://www.interactivebrokers.ie/en/pricing/market-data-pricing.php) is a later point-of-use check. Existing local hardware is sufficient for initial research; no VPS/colocation requirement is established.

## Paper and future expansion

The [Alpaca paper guide](https://docs.alpaca.markets/us/docs/paper-trading) documents simulated fills and omitted fees/impact/queue effects. The local adapter records zero simulated fees explicitly, never as a real-cost claim; cash differences halt. Actual account/calendar/asset/free IEX reads are verified, while actual paper orders/fills remain unverified. Paper is operational evidence, not achievable live profit. The retained IBKR code is inactive offline groundwork.

Crypto is deferred. Prior MES expired-contract/provider/quote research was removed with the dropped MES procurement plan (see Git history); it is not a prerequisite or purchase instruction for NVDA. Adding another market/source later requires a separately admitted configuration and regression tests through the same interfaces. No capital, account eligibility, risk limits, short inventory, paid subscription or strategy edge is established.
