# Providers, compatibility and cost discipline

Reviewed **2026-10-29** against the official sources linked below. This is a research procurement and compatibility plan. No broker connection, account inspection, paid request or trading test has been performed. Public documentation establishes advertised capabilities; account eligibility and actual data coverage remain unverified.

**Subsequent evidence:** M1's pinned offline engine/import compatibility is recorded in [M1_FOUNDATION.md](M1_FOUNDATION.md). M2a's more specific [provider decision](data/PROVIDER_COMPARISON.md) and [MES dataset](data/HISTORICAL_DATA_SPEC.md) govern the historical archive: IBKR's documented expiry limit cannot supply the six-year period; Databento historical PAYG is conditionally recommended, with an individual-contract FirstRate alternative. No paid source, quote, entitlement or retention right has been approved. The earlier checkpoints below remain background, not an instruction to repeat completed feasibility research.

## Selected roles

| Component | Decision | Qualification and cost policy |
| --- | --- | --- |
| Interactive Brokers (IBKR) | Selected broker; evaluate historical data first; IBKR Paper Trading at M6 | Confirm account entity, permissions, subscriptions and actual historical coverage before relying on access. |
| NautilusTrader | Leading simulation/execution framework, provisional pending M1 compatibility evidence | Select one coherent released version, Python version, adapter and matching documentation. Open-source software does not remove data or operating costs. |
| Parquet / DuckDB | Local historical storage / analytical queries | Keep dataset manifests in Git; market files and databases outside Git. DuckDB is not the operational order ledger. |
| pandas / Polars | Data processing | Use the tool justified by the task; avoid duplicate transformation pipelines. |
| scikit-learn, LightGBM, XGBoost | Core ML research capability at M4 | Begin with local CPU models and simple statistical comparisons; no GPU purchase is assumed. |
| Databento | Optional specialist historical provider | Evaluate only after a documented IBKR coverage gap. Quote the exact dataset, schema, symbols and period; purchasing requires authorization. |
| Alpaca | Future alternative for a justified market | Its documented equities/crypto API and separate options support are not evidence of an MES execution route. Recheck instrument and jurisdiction support before selection. |
| Other vendors, crypto venues, LLM services, VPS | Deferred | Select against a concrete research or operational need; no cloud or orchestration service is required for M0/M1. |

The [IBKR TWS API introduction](https://www.interactivebrokers.com/docs/tws-api/doc/introduction) documents a socket connection through TWS or IB Gateway. The [Alpaca Trading API overview](https://docs.alpaca.markets/us/docs/trading-api) and [options documentation](https://docs.alpaca.markets/us/docs/options-trading) support the narrower comparison above; they do not establish account-specific access.

## Framework compatibility gate

**Verified documentation mismatch:** the official [NautilusTrader installation guide](https://nautilustrader.io/docs/latest/getting_started/installation/) retrieved for this review describes 2.x release-candidate wheels and Python 3.13–3.14, while explicitly stating that an ordinary stable installation resolves the 1.x line and cannot run the 2.x examples unchanged. Context7 returned both older 1.x release material and current development material. Neither an indexed snippet nor a moving `latest` URL is a reproducible version choice.

The current [IBKR integration guide](https://nautilustrader.io/docs/latest/integrations/interactive_brokers/) documents TWS/Gateway connectivity, historical requests, live data and execution. Its described transport requires a sufficiently new server protocol; the adapter and server must be checked together. An open socket or correct default port does not prove compatibility. These observations are a reason to verify a version tuple, not to adopt a prerelease automatically.

**M1 evidence required before framework acceptance:** record the exact framework release, Python patch version, OS/architecture, dependency lock and matching documentation version; prove package and IB adapter import, synthetic MES instrument construction, and deterministic offline bar replay in pytest. Record the expected TWS/Gateway and transport requirements from that release. Test configuration isolation without broker credentials or network access. Defer any authenticated handshake to separately authorized integration work. A failed candidate is recorded with its error and alternatives; changing the preferred framework requires a decision review.

## Historical data: IBKR first, coverage before purchase

The current [IBKR market-data limitations](https://www.interactivebrokers.com/docs/tws-api/doc/md/market-data-limitations) establish the following constraints:

- Expired futures history older than two years **from expiration** is unavailable; this is not a guarantee of a complete two-year sample.
- Bars of 30 seconds or less older than six months are unavailable. The published small-bar pacing rules apply to that size class: repeated identical requests inside 15 seconds, six or more matching contract/exchange/tick-type requests inside two seconds, and more than 60 requests in ten minutes are violations; `BID_ASK` counts twice.
- Historical data is filtered and can be revised. Historical and real-time volume or VWAP may differ. Snapshot retrieval time and checksums rather than silently replacing earlier research inputs.
- Subscriptions and permissions constrain API data access. A paper account or delayed feed does not imply licensed real-time CME access.

The minute-bar pipeline must still use bounded requests, configurable pacing, retry/backoff and checkpointed resumption. Do not present a small-bar quota as the entire API's universal throughput limit.

**M2 acceptance evidence:** produce a contract-by-contract coverage matrix for the preregistered MES study period, including earliest/latest returned timestamps, requested/returned sessions, gaps, bar conventions, trade/quote availability, retrieval date, contract expiry, license/retention rights and subscription assumptions. Validate at least one contract roll, a daylight-saving transition and an early-close session. All duplicate, nonmonotonic, out-of-session or impossible OHLC records must be rejected or explicitly quarantined. Every expected session must be classified as accepted or excluded with a reason; do not fill a missing observation by copying future data.

If the available history cannot support the declared sample or execution assumptions, record the shortfall and its statistical impact. A smaller feasibility sample may answer a data-engineering question but cannot be relabeled as the planned confirmatory study. Request an alternative-data quote or revise the study transparently before testing.

Databento's [historical cost-estimation endpoint](https://databento.com/docs/api-historical/metadata/metadata-get-cost) returns an estimate in USD for the specified request and warns that some interval alignments can overestimate. Its [usage-pricing FAQ](https://databento.com/docs/faqs/usage-pricing-and-data-credits) explains metered historical billing and repeat-download differences. Check the applicable license, estimator parameters, expected bytes, spending ceiling and repeat-request policy before any download. Promotional credits and their eligibility are not a project funding assumption.

## Execution costs and units

CME specifies an MES multiplier of **USD 5 per index point** and an outright minimum tick of **0.25 index points**, so one tick is **USD 1.25 per contract**. Notional exposure is `5 × index level × contracts`; margin is collateral, not a maximum loss. See the [CME MES product page](https://www.cmegroup.com/markets/equities/sp/micro-e-mini-sandp-500.html) and [CME Micro E-mini FAQ](https://www.cmegroup.com/articles/faqs/micro-e-mini-equity-index-futures-frequently-asked-questions.html).

For a completed round trip, with quantity `q`, direction `d` in `{−1, +1}` and executed prices in index points:

```text
gross fill P&L (USD) = d × q × 5 × (exit_fill − entry_fill)
explicit fees = sum over fills of contracts × (broker + exchange + clearing + regulatory fees)
net trading P&L = gross fill P&L − explicit fees − applicable financing/FX/other charges
```

When fills are modeled from midprices, subtract spread crossing and adverse slippage exactly once. If the simulator already executes buys at ask and sells at bid, the spread is already in fill P&L. Slippage is measured relative to the declared executable benchmark, not added again to a fill that already includes it.

**Arithmetic example, not a price quote or performance result:** for one contract, assume USD 1.50 total explicit round-trip fees, a one-tick spread crossed across entry/exit (two half-spreads total), and one further tick of adverse slippage across the round trip. Friction is `1.50 + 1.25 + 1.25 = USD 4.00`. Breaking even against midprices requires `4.00 / 5 = 0.80` index points before those costs. With USD 2.50 assumed fees, two spread ticks and two slippage ticks, friction is USD 7.50. These are test scenarios, not observed fills or evidence of profitability.

Gemini's USD 1.22 round-trip fee estimate and USD 3.72 all-in example are unverified assumptions. The [IBKR futures commission schedule](https://www.interactivebrokers.com/en/pricing/commissions-futures.php) lists product-specific commission tiers separately from exchange/regulatory and some other charges. Determine the complete account-specific schedule; a headline broker commission is not the all-in cost. Stress test both fee changes and worse fills, including missed and partial execution, before drawing conclusions.

Research reports must show gross and net returns, trade count, turnover, exposure, drawdown and cost sensitivity. Separate fixed data/software/hosting costs from per-trade net P&L, then report total research/operating cost separately. For future equities include commissions, venue/regulatory charges, spread, borrow and corporate actions where relevant; for crypto include percentage maker/taker fees, spread, venue risk and funding for derivatives. None of these comparisons establishes a profitable market.

## Paper execution and operational costs

[IBKR's paper-account limitations](https://www.ibkrguides.com/advisorportal/aboutpapertradingaccount.htm) state that fills are simulated from top-of-book data and certain order types or complex-order behaviors differ from production. Paper testing demonstrates integration and process behavior; it cannot prove queue position, market impact or achievable live returns.

Budget for licensed real-time data, account/subscription eligibility, local machine uptime, secure credentials, recovery storage, monitoring and operator time. The [IBKR market-data pricing page](https://www.interactivebrokers.com/en/pricing/market-data-pricing.php) is the point-of-use tariff checkpoint; its content could not be retrieved during this review, so no current subscription tariff is asserted. Confirm nonprofessional/professional classification and the exact exchange/product entitlement rather than assuming eligibility.

IBKR documents [daily and weekly reauthentication](https://www.interactivebrokers.com/docs/tws-api/doc/tws-settings/daily-weekly-reauthentication). M6 must handle authentication expiry, scheduled restarts, missing/stale feeds, disconnects and reconciliation before resuming order submission. A VPS does not remove authentication duties. Keep a supported local setup until an observed availability need justifies hosting; no deployment is authorized by this document.

## Spending and unresolved decisions

| Stage | Planned resource use | Decision still required |
| --- | --- | --- |
| M0–M1 | Documentation, existing local hardware, synthetic data | Coherent framework/Python/adapter release tuple; no trading or paid downloads. |
| M2 | Authorized available IBKR history first | Coverage, access/license and study adequacy; exact alternative quote only if a gap is demonstrated. |
| M3–M5 | Local rule-based and CPU ML research, realistic simulation | Declared fee/fill scenarios, sample adequacy and out-of-sample evaluation. |
| M6–M7 | Separately authorized IBKR paper integration and multiple strategies | Account/market-data entitlements, risk limits, reliability and paper activation gates. |
| M8–M9 | Conditional LLM research and broader markets | Licensed news/filings, model/version retention, inference and evaluation budget, jurisdiction and instrument support. |
| M10 | Conditional live-readiness assessment | Explicit authorization, account/legal/tax review, loss limits and operating budget; readiness is not order authorization. |

No account domicile, tax residence, starting capital, margin requirement, fee tier, market-data subscription, paid vendor, LLM provider or hosting budget has been established. These must be resolved at the milestone that needs them. The [roadmap](ROADMAP.md) owns milestone status; [requirements](../REQUIREMENTS.md) own platform acceptance criteria.
