# Trading Bot — Essentials for Antonie

> Condensed from the supplied feasibility report. Focus: a solo developer on Ubuntu, with 16 GB RAM, building a bot that usually closes trades within an hour. This is a research plan, not evidence that any strategy is profitable. Exact fees, margins, product access, and regulatory claims in the original report have not been independently verified here.

## 1. What we are trying to build

An automated system that finds a repeatable trading advantage **after transaction costs**, with the same strategy logic used for historical testing and live execution.

- **Initial research target:** 5–15-minute bars, with positions typically held for 15–60 minutes. A bar summarizes prices over an interval; its length is separate from the position's holding period.
- **Not the initial target:** latency arbitrage, market making, or strategies whose profitability depends on beating other participants to a quote.
- **Success criterion:** credible performance on unseen data, realistic execution, and controlled losses—not a good-looking backtest.

The report calls minute scalping categorically infeasible. That is too broad: short holding periods are not automatically impossible, but costs and execution uncertainty become more important as the expected price move shrinks.

## 2. Choose one market first

| Candidate                  | Why consider it                                                               | Main constraint                                                                   | Role in the project                                         |
| -------------------------- | ----------------------------------------------------------------------------- | --------------------------------------------------------------------------------- | ----------------------------------------------------------- |
| Equity index micro futures | Exchange-traded contracts, compact research universe, fixed fees per contract | Leverage and minimum contract size can make even one contract too risky           | Main candidate if account size supports conservative sizing |
| BTC or ETH spot            | Accessible exchange data, fractional sizing, continuous trading               | Percentage fees, venue risk, and 24/7 operating demands                           | Alternative for small-size experiments                      |
| Liquid US stocks           | Broad research universe and established broker APIs                           | Minimum commissions, stock selection, corporate actions, and account restrictions | Add after the first pipeline works                          |

**Futures candidates:** MES is the Micro E-mini S&P 500 contract; MNQ is the Micro E-mini Nasdaq-100. European alternatives include FDXS, Micro-DAX, and FSXE, Micro-EURO STOXX 50.

Start with one instrument and one strategy. Defer options, funding arbitrage, prediction markets, and multiple venues.

**Margin is collateral, not maximum loss.** Low advertised intraday margin does not make a contract affordable. If one contract exceeds the chosen loss budget, keep it in simulation or choose an instrument that allows smaller positions.

## 3. Costs decide whether the strategy is worth testing

For each completed trade:

**Net profit = gross trading profit − commissions − exchange/regulatory fees − execution costs − applicable financing or funding.**

Execution costs include the **spread**, the gap between the best buying and selling quotes, and **slippage**, the difference between the intended and actual execution price. Avoid double-counting them if fills already use executable bid/ask prices.

Compare brokers using the full entry-and-exit cost, called a **round trip**, at your expected position size and order count.

- A fixed fee hurts smaller positions more as a percentage of capital.
- A percentage fee scales with the position's value.
- A limit order can reduce execution costs but may never fill. It can also fill just before the market moves against it.

**Illustration, not a fee quote:** a 0.05% charge on each side costs 0.10% per round trip. A gross move of 0.15% leaves only 0.05% before other costs.

Test ordinary costs and materially worse costs. A strategy that only survives ideal fills is not ready.

## 4. A practical software stack

| Component                  | Initial choice                          | Purpose                                                                |
| -------------------------- | --------------------------------------- | ---------------------------------------------------------------------- |
| Strategy and research code | Python                                  | Fast iteration and readable implementation                             |
| Backtesting and execution  | Evaluate NautilusTrader first           | Event-driven simulation and live execution using shared strategy logic |
| Alternative engine         | QuantConnect LEAN                       | Compare if its broker support or workflow fits better                  |
| Historical storage         | Parquet files partitioned by date       | Compressed, column-oriented data without a database server             |
| Data analysis              | Polars; DuckDB when SQL helps           | Transformations and analytical queries                                 |
| Broker candidate           | Interactive Brokers (IBKR)              | Evaluate actual eligibility, API support, data, and total costs        |
| Crypto alternative         | An eligible exchange with suitable APIs | Verify local availability and the exact trading pair's fees            |
| Tests and reproducibility  | pytest, Git, pinned dependencies        | Check calculations, execution behavior, and repeatable runs            |
| Research notebook          | Obsidian                                | Record hypotheses, experiments, rejected ideas, and decisions          |

Before committing to an engine, prove that the selected adapter supports the required instrument, data subscriptions, orders, reconnects, and paper account. A shared engine reduces duplicate code; it does not guarantee realistic fills.

Do not build a custom backtester or order-management engine initially. Add Redis, a server database, Rust modules, or more services only when a demonstrated need justifies them.

### Your laptop and internet connection

Your 16 GB machine is suitable for an initial bar-based workflow. Read selected columns and date ranges rather than loading years of tick data into memory. A graphics processor is not required for this baseline.

Start research and supervised paper sessions locally. Consider a VPS—a virtual private server—when unattended uptime becomes necessary. For the intended holding periods, measure signal-to-order delays and prioritize reliable connections, recovery, and monitoring before paying for specialized colocation.

## 5. Research before machine learning

Begin with a transparent hypothesis, for example:

- **Opening-range breakout:** does crossing the initial session's price range predict continuation after costs?
- **Intraday mean reversion:** do unusually large moves reverse under identifiable conditions?

Test one first. Define entry, exit, maximum holding time, sizing, and allowed trading hours before optimizing parameters.

Only then test whether machine learning improves the baseline. One candidate is **meta-labeling**: a simple rule proposes a trade, and a classifier estimates whether to take it. Keep it only if unseen-data results improve after costs.

Use Codex for implementation, tests, and review. Keep large language models out of the initial live order-decision path. Defer deep learning and reinforcement learning until simpler approaches justify further work.

## 6. Validation that matters

1. **Respect time.** Features must use information actually available when the decision occurs. A completed bar's closing price is unavailable before that bar ends.
2. **Use chronological development and testing.** Train or tune on earlier data, then evaluate on later periods. Preserve a final untouched holdout.
3. **Handle overlapping targets.** Purging removes training examples whose outcome windows overlap the test interval. An embargo excludes nearby observations when the information structure warrants it.
4. **Use CPCV later if useful.** Combinatorial Purged Cross-Validation tests multiple purged splits. It supplements chronological testing; it does not replace it or guarantee profitability.
5. **Model executable trades.** Include fees, spreads, slippage, partial fills, rejected orders, and unfilled limits where relevant. If a bar touches both a stop and a target, its high and low alone do not reveal which came first.
6. **Log every experiment.** Trying hundreds of variants and reporting only the winner creates selection bias. Fit scalers and model parameters using training data only.
7. **Test robustness.** Compare periods and market conditions, nearby parameter settings, delayed entries, and worse costs.

Track net profit, trade count, profit per trade, drawdown, exposure, turnover, and cost sensitivity. **Drawdown** is the decline from a previous equity peak. **Sharpe ratio** measures average excess return relative to return variability; a high historical value alone is insufficient evidence.

## 7. Build order and promotion gates

| Stage                   | Deliverable                                                        | Gate before continuing                                                             |
| ----------------------- | ------------------------------------------------------------------ | ---------------------------------------------------------------------------------- |
| Scope                   | One instrument, broker candidate, holding horizon, and loss budget | Verify account access, costs, data availability, and viable position sizing        |
| Data                    | Repeatable ingestion with timestamps and quality checks            | Detect gaps, duplicates, session errors, and relevant adjustments or futures rolls |
| Baseline                | One strategy with a cost-aware backtest                            | Reproducible results and credible performance on unseen periods                    |
| Paper trading           | Live data, simulated orders, logs, and recovery                    | Explain differences from historical simulation and verify operating controls       |
| Minimum-size live trial | Smallest position consistent with the loss budget                  | Measure actual fills, costs, and failures before considering scaling               |

Paper trading validates operation, not live fill quality. A fixed number of sessions or an arbitrary percentage agreement with a backtest does not prove an edge.

Before live trading, implement position limits, daily loss limits, stale-data detection, duplicate-order protection, a kill switch, and broker reconciliation after reconnects. Persist orders, executions, fees, positions, and currency conversions for analysis and reporting.

## 8. What to verify from the original report

Do not base account funding or market selection on its unverified specifics:

- Claimed abolition of the US Pattern Day Trader rule, replacement margin rules, and applicability to the actual broker entity.
- Exact broker commissions, exchange charges, data subscriptions, fee waivers, and margins.
- Eligibility for US ETFs, crypto derivatives, professional classification, and local tax treatment.
- Current engine/adapter capabilities and data-vendor coverage.
- Claims that a particular data-center location guarantees a particular execution latency.

**Immediate next step:** establish starting capital and the maximum acceptable loss per trade, then evaluate one instrument and obtain a small data sample. Prove the simplest strategy-testing loop before expanding the infrastructure.
