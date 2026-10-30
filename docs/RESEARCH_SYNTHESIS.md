# Research synthesis

**Scope update, 2026-10-30:** active research is NVDA with Alpaca history and IBKR execution; crypto is deferred. MES/SPY and vendor comparisons below retain their original research context. [Current protocol](../experiments/exp001_itsm/README.md) and [NVDA plan](data/NVDA_DATA_PLAN.md) govern new work; no prior paper result proves NVDA alpha.

Reviewed 2026-10-29. This document evaluates the supplied research; it contains no project backtest results. Requirements and decisions remain authoritative in [REQUIREMENTS.md](../REQUIREMENTS.md) and [DECISIONS.md](DECISIONS.md).

## Evidence and provenance

All three Gemini reports were reviewed in full. Originals are retained unchanged with their supplied SHA-256 checksums:

| Original | Main contribution | Treatment |
| --- | --- | --- |
| [01: Broad feasibility](research/original/gemini_01_broad_feasibility.txt) | Market, broker, infrastructure and storage survey | Useful problem inventory; many precise fees, margins, latency and regulatory conclusions need correction or verification. |
| [02: Horizon and strategy comparison](research/original/gemini_02_horizons_strategy_comparison.txt) | 5–60 minute strategies, ORB, cost decomposition, ML filters | Candidate hypotheses; neither excursion-to-cost ratios nor model rankings prove an edge. |
| [03: Empirical short horizon](research/original/gemini_03_empirical_short_horizon.txt) | Challenges unconditional ORB; motivates intraday momentum | Stronger motivation for EXP-001, with important return-definition and evidence-transfer caveats. |

The previous standalone `firstResearch.md` was an editorial condensation of report 01, rather than another original research report. Its useful cautions about costs, ambiguous bars, sizing, paper fills and overfitting are incorporated here and in the final specifications. It contained no additional primary empirical dataset or study.

Labels below mean **verified fact** (supported by a retrieved primary source), **reported finding** (a study's historical conclusion, not reproduced here), **hypothesis** (to be tested), and **open question** (insufficient evidence). Public documentation was checked on the review date; mutable pages and account-specific conditions must be rechecked before implementation or spending. An access date does not establish when an undated page changed.

## Market and horizon selection

**Decision:** start with MES and approximately 30-minute intraday holding periods. This bounds one experiment and makes costs and execution assumptions visible. It is not a universal ranking of markets or a conclusion that MES is affordable for a particular account.

| Market | Research appeal | Limitation and project disposition |
| --- | --- | --- |
| CME index micro futures | Small instrument universe; exchange contract definitions; directional and session hypotheses | Integer contract sizing, leverage, expiry, roll and USD exposure. MES first; other futures require separate evidence. |
| US individual equities | Cross-sectional momentum, catalyst selection and finer sizing | Corporate actions, delistings, universe selection, borrow, minimum fees, account permissions and margin rules. Later expansion. |
| European equities and UCITS ETFs | EUR exposure and regional research | Venue/session differences and full trading costs must be measured; blanket dismissal is unsupported. |
| Crypto spot | Fractional sizing, continuous data and alternative regimes | Venue risk, percentage fees, eligibility and 24/7 operation. High fees can erase small conditional returns; no universal impossibility theorem follows. |
| Crypto derivatives, options, FX and prediction markets | Different payoffs and research questions | Additional product, venue and operational complexity. Outside the initial experiment. |

**Verified fact:** CME specifies MES as $5 times the S&P 500 index, with a 0.25-index-point minimum outright tick, worth $1.25. Notional exposure is index level times $5, independently of margin posted. Exchange and broker margin snapshots in the reports are not position-risk limits. [CME product specification](https://www.cmegroup.com/markets/equities/sp/micro-e-mini-sandp-500.html).

Holding period, feature/bar interval and execution-data resolution are separate choices. A 30-minute hold can use one-minute features and quote-level execution. Longer horizons may reduce costs relative to typical variation, but variation is not expected profit conditional on a signal. No source here validates the reports' precise “safe capital” tiers, universal scalping prohibition, or guaranteed post-cost viability.

## Intraday momentum and EXP-001

**M2a follow-up:** the [dataset specification](data/HISTORICAL_DATA_SPEC.md#2-what-the-academic-signal-actually-is) records an inspectable original-author manuscript's r1/r12/r13 and sign-agreement strategy, including its zero-return convention and the remaining published-final-methods retrieval limit. Use that bounded evidence rather than repeating the same paper discovery. The accepted MES rule is unchanged.

**Reported finding:** Gao, Han, Li and Zhou study S&P 500 ETF observations from 1993–2013 and report that the return from the **previous day's close to the end of the first half hour** predicts the final half-hour return. This includes overnight information. Report 03's description of the first return as only 09:30–10:00 ET omits that distinction. The paper's abstract also reports stronger predictability in particular volatility, volume and news conditions. These historical findings do not establish modern MES profitability. [Gao et al., 2018, publisher abstract and introduction](https://www.sciencedirect.com/science/article/pii/S0304405X18301351).

**Reported finding:** Li, Sakkas and Urquhart examine 16 developed markets, finding economically and statistically significant ITSM in most markets, with links to liquidity, volatility and information continuity. The published article is titled *Intraday time series momentum: Global evidence and links to market characteristics*; the supplied report uses an earlier working title. International historical evidence supports investigation, without validating an exact MES execution rule. [University of Nottingham publication record](https://nottingham-repository.worktribe.com/output/5273197).

**Hypothesis:** a low-turnover MES sign-agreement adaptation can produce positive returns after realistic costs in unseen data. The provisional signals use previous cash close to 10:00 ET and 15:00–15:30 ET; agreement proposes direction for the final half hour. This is an adaptation, not a verified replication of either paper. The experiment protocol must specify the actual contract, cash-close proxy, previous-session mapping, early closes, roll handling, signal availability and executable entry after inputs become known. A 15:30 completed price cannot also guarantee a fill at that same price. [EXP-001 protocol](../experiments/exp001_itsm/README.md).

The reports' exact R-squared values, annualized returns, certainty-equivalent gains and crisis coefficients have not been reproduced against the original study tables or our target data. They are not project performance targets. Proposed rebalancing and hedging explanations remain mechanisms to investigate; asserting that nearly all relevant information arrives before the open is unjustified.

## Other strategy families and conflicting evidence

- **Opening-range breakout:** report 02 ranks futures ORB first; report 03 treats unconditional futures ORB as broadly falsified. Neither conclusion transfers across instruments, selection rules, stops, data or costs without replication. The authors of the equity “Stocks in Play” study describe a selected-stock ORB experiment, rather than proof for static MES/MNQ. Its historical results are reported findings only. [Original authors' research catalogue](https://concretumgroup.com/papers/).
- **Unverified ORB numbers:** the named 2026 Fetna/Mesfin/Subhani studies, 225-cell result, precise replication slippage thresholds and practitioner profit factors were not verified to a sufficiently inspectable primary method during this review. Searches are not proof those works do not exist. Retain them as research leads, without using their figures as acceptance gates or declaring all ORB profitable/unprofitable.
- **Mean reversion, trend, statistical arbitrage and volatility breakouts:** retain as distinct hypotheses after the baseline. Define session, regime, risk and cost assumptions first. Pair strategies must include both legs' costs and failed/partial hedges. No empirical diversification follows merely from different names or holding periods.
- **Order-book imbalance:** short-lived microstructure effects may help execution or research, but the reports' assertion of exactly zero predictive information at every 5–60 minute horizon is not established. Do not require L2/L3 infrastructure until an experiment demonstrates a need.

## Costs, providers, brokers and simulation

The [cost and provider assessment](COSTS_AND_PROVIDERS.md) owns procurement criteria and current technical checks. Preserve these research conclusions:

1. Compare conditional **net** return with costs, not average bar range with commission. Costs include broker and venue fees, spread, slippage, financing/borrow/funding where applicable, FX and fixed operating overhead. Use account-, instrument- and date-specific schedules.
2. Avoid double-counting spread when PnL already uses executable bid/ask fills. Passive orders require a non-fill/adverse-selection model; “maker fee only” is not a complete execution assumption.
3. The reports contain arithmetic errors. In report 02, $5 on a $5,000 ticket is **10 bps**, while 1 bp is $0.50. In report 03, $0.01 spread times 100 shares is $1; a round trip benchmarked to unchanged midpoint generally pays one full spread, rather than two. Recompute every example before reuse.
4. The reports' $1.22 MES round-trip fee and $3.72 total friction are historical claims/scenario inputs, not verified current all-in quotes. A modeled slippage allowance is not a measured execution distribution.

**Verified price snapshot:** Kraken's retrieved general spot schedule lists Tier 1 maker/taker rates of 0.40%/0.80% and Tier 3 rates of 0.22%/0.38%. Report 03's 0.20% Tier 3 maker rate conflicts with that page. Product, pair, regional schedule and promotions can differ; these rates do not establish another venue's costs or a universal prohibition on spot research. [Kraken fee schedule](https://www.kraken.com/features/fee-schedule).

IBKR remains the selected broker and first historical-data feasibility candidate. Alpaca remains a future alternative; its official Trading API overview describes equity/crypto trading and paper simulation, which alone does not demonstrate suitability for the MES experiment. Specialized futures brokers and crypto venues require separate adapter, eligibility, cost and recovery evaluation. No account was connected. [Alpaca Trading API overview](https://docs.alpaca.markets/us/docs/trading-api).

Historical bar depth, expired-contract access, missing records, market-data rights and pacing can make IBKR insufficient for a particular study. Test that gap before considering Databento, FirstRate Data or other providers. Advertised free credits, price estimates and broad historical coverage in the reports have not established complete, licensed MES research data.

**Verified timestamp fact:** raw Databento OHLCV `ts_event` denotes interval start; no-trade intervals need not print bars. The reports conflate this with adapter conversion settings. Preserve original timestamps and separately represent when a completed bar becomes available; confirm the selected adapter's behavior on a small sample. [Databento OHLCV schema](https://databento.com/docs/schemas/ohlcv).

**Verified framework capability:** NautilusTrader documents shared backtest/live core components. This supports the chosen architecture; it does not guarantee identical fills, lossless recovery or zero live/backtest divergence. The reports' broad claims that all default orders fill at bar close are also too coarse. Bar-based execution reconstructs a synthetic path, which cannot reveal actual intrabar stop/target order. Verify fill, fee, latency and data-ordering behavior for the pinned release. [Nautilus backtesting](https://nautilustrader.io/docs/latest/concepts/backtesting/), [bar execution](https://nautilustrader.io/docs/latest/concepts/backtesting/bar-execution/).

LEAN is a credible fallback if compatibility fails: official documentation supports local as well as cloud IBKR execution, so describing it as cloud-only would be incorrect. VectorBT provides vectorized research and backtesting; it is a screening alternative, not the selected execution engine. Reconsidering engines requires a concrete gap, rather than the reports' unverified speed or superiority claims. [LEAN IBKR documentation](https://www.quantconnect.com/docs/v2/lean-cli/live-trading/brokerages/interactive-brokers), [VectorBT documentation](https://vectorbt.dev/).

**Verified simulator limitation:** IBKR documents simulated top-of-book fills, unsupported order types and differences in stop/complex-order behavior. Paper trading tests operation and reconciliation; it cannot validate actual queue priority, realized slippage or an economic edge. The reports' 20-session, 5%-parity and 60-live-session promotion rules have no sufficient justification here. [IBKR paper account limitations](https://www.ibkrguides.com/advisorportal/aboutpapertradingaccount.htm).

## Machine learning, LLMs and validation

ML is a core platform research capability. Independent predictive agents and rule-plus-ML filters are both supported. Start comparison with a simple linear/logistic baseline, then assess scikit-learn models, LightGBM and XGBoost on the same chronological information sets. The reports do not establish universal dominance of boosting, guaranteed probability calibration from logistic regression, or permanent inferiority of LSTM/Transformers. Deep learning and reinforcement learning require a justified experiment and resource budget.

Meta-labeling is a candidate use case, not a necessary architecture for all ML. Record feature availability, label start/end times and model training cutoff; fit preprocessing, calibration and hyperparameters within training folds. Evaluate discrimination, calibration, turnover, cost-aware economic results and stability against the unfiltered baseline. Labels derived from future outcomes belong only in training/evaluation.

Use chronological development, walk-forward evaluation and a final untouched holdout. Purge overlapping label intervals and choose any embargo from actual information overlap and dependence. A fixed “1%” or “one session” buffer is not universally correct. CPCV may supplement this analysis; training on later periods in a combinatorial split must not be presented as deployable walk-forward forecasting. Prefix-invariance checks should compare decisions whose inputs and outcomes are fully observable before the truncation boundary.

Log all trials and failed experiments. Bailey and López de Prado's Deflated Sharpe Ratio addresses selection bias and non-normality; its assumptions, return frequency, effective trial count and sample uncertainty matter. A 0.95 threshold is a possible preregistered decision rule, not a proof of profitability or a universal legal requirement. Avoid transplanting the reports' formulas, trial counts and numerical examples without verification. [Original authors' DSR paper record](https://papers.ssrn.com/abstract=2460551).

LLM agents are an accepted future capability for source-grounded research and structured event/sentiment assessment. The reports provide no validated LLM trading edge. Text must have publication and availability timestamps, revisions and source provenance; model evaluation must control retrospective knowledge and point-in-time access. External text is untrusted. LLM outputs stay advisory and pass through deterministic validation, portfolio coordination and central risk; they receive no brokerage execution authority.

## Regulatory and operational corrections

**Verified fact:** FINRA's replacement intraday margin standards became effective June 4, 2026, with broker transition permitted through **October 20, 2027**. Firms may still apply the previous rules during that interval. FINRA describes intraday maintenance requirements and broker discretion, contradicting the reports' categorical completed repeal at every broker and uniform 2x intraday leverage. Determine the carrying entity and actual account rules before an equity experiment. [FINRA investor guidance](https://syndication.finra.org/content/understanding-new-intraday-margin-requirements).

**Verified correction:** IBKR announced EEA crypto-asset trading for eligible individual investors through IBIE on March 31, 2026. Report 03's categorical assertion that IBIE does not offer spot crypto is outdated or incorrect. This announcement does not establish our account, residence, instrument or API eligibility. [IBKR official press-release archive, March 31 entry](https://investors.interactivebrokers.com/en/general/about/press-releases.php).

The EU PRIIPs framework requires product disclosure; futures are not categorically outside it merely because they are not ETFs. Verify actual KIDs, client classification, product permissions and broker distribution restrictions. Do not use options assignment or professional reclassification as an assumed workaround. [European Commission PRIIPs explanation](https://finance.ec.europa.eu/consumer-finance-and-payments/retail-financial-services/key-information-documents-packaged-retail-and-insurance-based-investment-products-priips_en).

MiCA distinguishes crypto-assets from instruments already governed by financial-services legislation. A spot-service authorization does not establish permission to distribute every crypto derivative. The reports' blanket exchange-licensing claims, PFOF business-model predictions, tax rates, investor-compensation comparisons and broker account eligibility were not comprehensively verified. They remain open questions for an instrument/entity/jurisdiction-specific review before market expansion. [MiCA regulation](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32023R1114).

Reports 01 and 03 prescribe colocation while report 02 allows local research/paper operation. No retrieved evidence makes colocation necessary for this experiment. Measure signal availability, feed delay, broker acknowledgements and recovery behavior. A ratio of network delay to holding period does not establish harmless slippage; ECC RAM, Redis or a VPS does not guarantee uptime or position parity. Future operations require stale-data controls, durable order/fill records, reconciliation, safe restart and a kill switch before unattended exposure. Stop orders and broker-held protection need explicit venue/adapter verification; they are not guaranteed loss caps.

## Open questions and next evidence

| Question | Evidence required before relying on it |
| --- | --- |
| Does ITSM survive on recent MES after costs? | Frozen EXP-001 protocol, data manifest, chronological holdout, conservative fills/cost sensitivity and uncertainty estimates; a negative result is valid. |
| Does the chosen framework/adapter support the required workflow? | M1 pinned-version compatibility record and offline tests; M6 separately authorized paper checks. |
| Is IBKR historical data sufficient? | M2 contract-by-contract availability/quality audit, request bounds and rights; obtain a vendor quote only for a documented gap. |
| How should MES proxy/roll definitions map to the papers? | Original study methods, explicit prior cash-close series, causal contract mapping and expiry-session policy before labeling a replication. |
| Does ML add incremental value? | Shared split boundaries, train-only transforms, calibrated outputs, full trial ledger and net OOS comparison with simple baselines. |
| Are future products and live operation suitable? | Actual permissions, current fees/margin, jurisdiction review, capital/risk limits and later explicit live authorization. |

The next implementation work is the M1 offline foundation and compatibility proof. Research claims remain falsifiable; no strategy, model, broker connection or order is implemented by this initialization.
