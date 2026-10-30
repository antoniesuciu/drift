# Quant Trading Lab: essential feasibility audit

Reviewed **2026-10-30** against commit `376009101a213d680f44d1a800552f4f2feedebb`. Public research and offline inspection only. No account access, market-data acquisition, installation, orders, commit or push. The user subsequently confirmed the scope below. A documentation-only update on 2026-10-30 aligned core requirements, architecture, roadmap and the [NVDA data plan](data/NVDA_DATA_PLAN.md); runtime NVDA admission remains unimplemented.

## Confirmed scope — user decision, 2026-10-30

**Alpaca for NVIDIA (NVDA) historical data; IBKR for trading NVDA shares. Crypto is out of scope for now**, including crypto research, ingestion and execution work. This supersedes the earlier AAPL-first and crypto recommendations. Keep Python/Nautilus/Parquet; no platform rewrite or paid historical archive is justified now. The source/broker/instrument choice does not itself authorize account connections or orders.

| Stage | Verdict | Essential condition |
| --- | --- | --- |
| Offline engineering | **GO** | Preserve the working synthetic pipeline. |
| Free-data research | **CONDITIONAL GO** | Verify applicable rights, access and delivered coverage. |
| IBKR paper now | **NO-GO now; feasible later** | Strategy/risk execution path, permissions and live feed remain untested. |
| Real money now | **NO-GO now; conditional later** | No measured net edge or validated execution exists. |

**Alpaca is the strongest initial free stock-data candidate reviewed:** historical SIP older than 15 minutes, coverage advertised since 2016, 200 requests/minute. Set `feed=sip`; free live streaming is IEX. Archival rights and actual completeness remain unverified. [Plans](https://docs.alpaca.markets/us/docs/about-market-data-api), [FAQ](https://docs.alpaca.markets/us/docs/market-data-faq). Historical archives support backtests; trading requires a current feed, not month-old prices.

**NVDA is the sole initial trading instrument.** Validate its split history, raw price/share units, costs and completed-candle availability before a rule backtest. The choice is a scope decision, not evidence that NVDA has superior strategy returns. Other products and crypto remain in the appendices as audit evidence, not active recommendations.

### Corrections and next approvals

| Priority | Correction | What it blocks |
| --- | --- | --- |
| **P0** | Confirm Alpaca NVDA rights/coverage and exact IBKR stock permissions. | Real-data admission and trading claims. |
| **P0** | Current code accepts synthetic MES only. Add NVDA source/instrument metadata narrowly when authorized. | NVDA ingestion, not existing offline tests. |
| **P1** | Use actual stock commissions, spread/slippage and any short borrow; validate the IBKR stock route. | Paper/live promotion. |
| **P1 — resolved in specifications** | Preserve the existing **2020–22 / 2023 / 2024–25** split. The audit's proposed alternative was not adopted. | Parameters/costs still need freezing before results. |
| **P2** | Replace download-speed, complete-data and stock-ranking claims with measurements. | Unsupported conclusions; no infrastructure expansion needed. |

**Source, broker and instrument choices are confirmed, and core specifications now align.** The split is preserved. Next tasks remain narrow offline NVDA implementation and a separately authorized rights-cleared pilot, following [NVDA-001–010](data/NVDA_DATA_PLAN.md#acceptance-gates). Pilot acceptance: hashes/full pagination, explicit gaps, NVDA split-boundary fixtures, native catalog/replay round-trip, future-data invariance and measured resources. Only afterward authorize one preregistered, cost-stressed NVDA rule backtest. Account review, connectivity, paper orders and live money each remain separate approvals.

The audit and subsequent scope alignment contain no implementation. M2 now follows the NVDA admission gates and M3 the NVDA baseline; the three families remain; ML/LLM selection, orchestration and deployment wait. The following appendices retain the supporting evidence for review.

## Appendix A — platforms and tradability

Evidence labels describe public facts: **verified**, **conditional** on stated prerequisites, **prohibited** under the stated product rules, or **unverified**. None means this user's account was tested. All external sources were accessed **2026-10-30**; effective dates are noted where known.

### Research versus IBKR paper/live

Main scenario: Romanian-resident, nonprofessional EU retail. Nationality and workstation timezone do not establish residence, legal entity, permissions or account type.

| Product/action | Historical research | IBKR paper | IBKR live execution requirement |
| --- | --- | --- | --- |
| SPY ETF opening buy | **Conditional:** Alpaca access/rights/coverage | **Unverified:** do not assume simulation bypasses live restrictions | **Prohibited** for the assumed ordinary retail purchase without required KID; no qualifying KID established |
| SPY sell existing holding | **Conditional:** same research data | **Conditional:** holding and simulator permission | **Conditional:** broker policy permits closing restricted holdings; actual holding/contract untested |
| SPY opening short | **Conditional:** simulated short can be researched, clearly hypothetical | **Unverified** for this account/product | **Unverified:** KID treatment, short permission and borrow must all be resolved |
| SPY share CFD | **Conditional:** SPY benchmark alone is insufficient execution data | **Conditional:** exact permitted CFD and simulator | **Conditional:** restricted-ETF CFD family exists; exact SPY conid, unit/multiplier, Romanian KID, quote, borrow and permissions unresolved |
| MES futures long/short | **Conditional:** actual dated contracts/calendar; free spot proxies are insufficient | **Conditional:** futures permission, contract/feed | **Conditional:** KID/appropriateness, whole-contract size and broker margin; notional is not posted collateral |
| SXR8 UCITS long/short | **Conditional:** own venue history required | **Conditional:** fund/route/feed | **Conditional:** KID and route; short additionally needs margin/borrow; late-session liquidity unmeasured |
| AAPL, NVDA, TSLA, AMD; optional MSFT/AMZN buys/day trades | **Conditional:** Alpaca feed/rights/coverage | **Conditional:** stock permission and matching account configuration | **Conditional:** direct shares avoid ETF PRIIPs packaging issue; cash settlement or applicable margin regime still matters |
| Same stocks short | **Conditional:** include realistic short costs and availability | **Conditional:** margin/short configuration; simulated borrow is not live availability | **Conditional:** margin, broker approval and available borrow; cash accounts cannot short |
| BTC / ETH IBIE spot buy/sell owned coin | **Conditional:** venue/pair mismatch and rights | **Unverified:** exact ZEROHASHE simulator support | **Conditional:** IBIE EEA onboarding/crypto permission, fully funded, route/order support |
| BTC / ETH IBIE spot opening short | **Conditional:** hypothetical research only | **Unverified:** simulator is no permission proof | **Prohibited:** IBIE addendum forbids crypto shorting/credit |
| MBT / MET futures long/short | **Conditional:** actual contracts; neither micro existed in 2020 | **Conditional:** permitted contract/feed/simulator | **Conditional:** futures permission, KID, collateral, integer lot size and roll costs |

The policy evidence is [PRIIPs recital 7 and Arts. 5–7](https://eur-lex.europa.eu/legal-content/EN/ALL/?uri=CELEX%3A32014R1286), [IBIE ETF/CFD policy](https://www.interactivebrokers.ie/en/trading/products-cfds.php), [IBKR closing-only explanation](https://www.interactivebrokers.com/campus/trading-lessons/trading-overseas-with-ibkr/), [shorting rules](https://www.interactivebrokers.com/campus/trading-lessons/short-selling-and-margin/), [paper-account limitations, updated 27 October 2026](https://www.ibkrguides.com/clientportal/aboutpapertradingaccounts.htm), and [IBIE crypto addendum 4871, 27 March 2026, §5A](https://ndcdyn.interactivebrokers.com/Universal/servlet/Registration_v2.formSampleView?formdb=4871). Action for the confirmed scope: verify NVDA/IBKR permissions; other rows remain reference evidence.

**Three access corrections matter:**

- **PDT:** FINRA's replacement intraday-margin rules took effect **4 June 2026**, with broker transition through **20 October 2027**. IBKR explicitly warns some accounts remain on the old rules during transition. Neither blanket “no PDT” nor blanket “$25k always required” is justified for an unidentified account. Cash-account settlement restrictions remain separate. [FINRA 26-10](https://www.finra.org/rules-guidance/notices/26-10), [IBKR transition](https://www.ibkrguides.com/orgportal/messagecenter/supportpdtreset.htm).
- **UCITS hours:** gettex currently publishes **07:30–23:00 Berlin time**. Xetra added extended retail hours in December 2025, but its current broker table does not show IBKR participating in the extended window. Thus “all UCITS markets are closed” is false; an executable late IBKR SXR8 route is still unverified. Anchor the target to **15:30–16:00 America/New_York**, handling unequal US/EU DST weeks. [gettex](https://www.gettex.de/en/extended-trading-hours/), [Xetra broker table](https://live.deutsche-boerse.com/en/xetra).
- **Jurisdiction:** Romania's listed KID language is Romanian; a generic English KID does not prove admission. Another EEA residence can change products: Belgium restricts electronic distribution of leveraged OTC derivatives to consumers. Professional status must never be assumed or used as an automatic workaround. [ESA language table, updated 5 December 2025, Romania p.8](https://www.esma.europa.eu/sites/default/files/2024-07/JC_2024_44_Table_MS_language_ex_ante_notification_PRIIPs_KID_CL.pdf), [Belgian FSMA](https://www.fsma.be/en/cfd).

### Execution-platform comparison

| Platform | EU/Romanian position and product distinction | API / current pinned integration / operational constraint | Decision |
| --- | --- | --- | --- |
| **IBKR** | Equity candidate; margin shorts conditional. IBIE spot BTC/ETH documented since **31 March 2026**, fully funded long-only. Futures separate. | Pinned Python IB adapter present. TWS/Gateway restart and weekly reauthentication; reconcile orders/fills/positions after disconnect. Paper uses simulated top-of-book fills. | **Keep for stocks.** Do not force crypto through it. |
| **Alpaca** | Free data/paper documented; direct Romanian live brokerage admission **unverified**. July 2026 EEA passporting announcement concerns partner infrastructure. | REST/WS; no Alpaca Python adapter in installed 1.231.0. Historical REST reader does not require a live broker adapter. Current Alpaca margin policy differs from IBKR transition policy. | **Use as data candidate**, not an assumed second live broker. |
| **Binance** | Public research archives verified. Current Romanian execution/entity/product eligibility **unverified**; June 2026 Greek MiCA application withdrawal is not proof of present prohibition or permission. Spot, margin and futures remain separate. | Pinned Python adapter present; technical availability does not establish legal access. REST endpoint weights/429/backoff; uncertain order timeouts require status reconciliation. | Alternative only after current Romanian authorization and fees are verified. |
| **Coinbase Advanced** | MiCA Romanian migration documented **13 October 2025**. Spot ownership permits selling held coins, not automatic naked shorts. EU entry fees **0.25% maker / 0.50% taker** from **16 September 2026**. | REST/WS. Advanced sandbox is static mocks. Tagged Coinbase adapter is Rust/v2; no legacy Python TradingNode integration in our installed stack. | Prior crypto recommendation; **deferred by the confirmed scope**. |
| **Kraken Pro** | EEA/Romania documented. Entry spot **0.40% / 0.80%** versus derivatives **0.02% / 0.05%**. Current consumer margin exclusion does not automatically settle separate regulated derivatives eligibility. | Pinned Python adapter present. Tiered REST/matching limits; nonce/reconnect handling. **29 October 2026** page says old public futures demo retired; replacement testing requires qualification. | Useful adapter/data alternative; **higher spot costs weaken the initial trading case**. |

Sources/actions: [IBIE crypto offering](https://www.interactivebrokers.ie/en/trading/products-crypto-assets.php), [IBKR reauthentication](https://www.interactivebrokers.com/docs/tws-api/doc/tws-settings/daily-weekly-reauthentication), [Alpaca EEA announcement](https://alpaca.markets/blog/alpaca-completes-eea-passporting-to-29-countries-expanding-access-to-regulated-investment-services-across-europe/), [Alpaca country support](https://alpaca.markets/support/countries-alpaca-is-available), [Binance European update, 24 June 2026](https://www.binance.com/en/blog/regulation/4457979419755346760), [ESMA CASP register](https://www.esma.europa.eu/esmas-activities/digital-finance-and-innovation/markets-crypto-assets-regulation-mica), [Coinbase MiCA](https://help.coinbase.com/en/coinbase/other-topics/other/mica-cblu), [Coinbase regional fees](https://www.coinbase.com/blog/were-lowering-fees-for-many-active-traders-on-coinbase-advanced), [Coinbase sandbox](https://docs.cdp.coinbase.com/coinbase-app/advanced-trade-apis/sandbox), [Kraken fees](https://support.kraken.com/articles/cross-platform-fee-tier-changes), [EEA terms, effective 14 October 2026, Part K](https://www.kraken.com/legal/eea-terms), [current Kraken testing notice](https://support.kraken.com/articles/360024809011-api-testing-environment-derivatives). Confirm the account-specific uncertainties before selecting execution.

Pinned support was checked in the installed wheel and [tagged IB](https://github.com/nautechsystems/nautilus_trader/blob/v1.231.0/docs/integrations/ib.md), [Kraken](https://github.com/nautechsystems/nautilus_trader/blob/v1.231.0/docs/integrations/kraken.md), and [Coinbase](https://github.com/nautechsystems/nautilus_trader/blob/v1.231.0/docs/integrations/coinbase.md) documentation through Context7. Newer 2.x documentation cannot establish our current compatibility.

Recent [September 2026 TWS reconnect discussion](https://www.reddit.com/r/algotrading/comments/1w717du/connecting_with_ibkr_tws_api/) and [August 2026 paper complaints](https://www.reddit.com/r/algotrading/comments/1vi7087/ibkr_paper_api_unreliable_and_inconsistent/) identify failure cases, not universal defects. Official [open-order](https://www.interactivebrokers.com/docs/tws-api/doc/order-management/open-orders) and [order-status](https://www.interactivebrokers.com/docs/tws-api/doc/order-management/order-status) documentation supports testing reconciliation and duplicate/missing callbacks. No community profitability claim is adopted.

## Appendix B — cost comparison

These are **scenarios, not observed spreads or returns**. EUR/USD = **1.10 assumed**, prefunded trading currency, one filled order each side, lowest published tier, no leverage interest or borrow unless stated. Current fees are not historical 2020–2025 schedules. At every exposure below, the same hurdle applies to **5-, 15- and 30-minute** holds unless a funding/financing boundary is crossed.

### Published fee inputs and scenario assumptions

| Product | Fee inputs | Spread/slippage scenario |
| --- | --- | --- |
| IBKR US shares Tiered | $0.0035/share, $0.35/order minimum; add venue/clearing/regulatory charges | Hypothetical $100 share; 11/55/110 shares. Full spread 1 bp + slippage 1 bp/side = **3 bp RT** |
| IBKR US shares Fixed | $0.005/share, $1/order minimum; conservative separate SEC/CAT | Same stock scenario |
| Generic US share CFD | $0.005/unit, $1/order minimum, exchange/regulatory included | Same hypothetical $100/unit; **not a verified SPY CFD specification** |
| German UCITS | Tiered 0.05%, €1.25/order minimum; Fixed SMART 0.05%, €3 minimum | Hypothetical €100 unit; full spread 10 bp + slippage 1 bp/side = **12 bp RT**; Tiered assumes SMART fills on gettex with no external fee, not directed Tiered access |
| IBIE spot crypto | 0.18%/side; $1.75 minimum capped at 1% of order value, nonbinding at these sizes | Full spread 2 bp + slippage 2 bp/side = **6 bp RT** |
| Coinbase Advanced EU spot | Maker 0.25%; taker 0.50%/side | Taker: same 6 bp RT; maker: fee-only lower bound, no guaranteed fill |
| Kraken spot | Maker 0.40%; taker 0.80%/side | Same taker scenario / maker lower bound |
| Kraken derivatives, conditional | Taker 0.05%/side, plus funding | Same 6 bp RT; not spot fees or proof of eligibility |

Sources: current [IBIE stocks](https://www.interactivebrokers.ie/en/pricing/commissions-stocks.php), [NASDAQ removal charge $0.003/share scenario](https://www.interactivebrokers.ie/en/accounts/fees/INETstkfee.php?nhf=T), [gettex external fees](https://www.interactivebrokers.ie/en/accounts/fees/GETTEXStkFees.php?nhf=T), [CFD commissions](https://www.interactivebrokers.ie/en/pricing/commissions-cfd-share.php), [IBKR crypto](https://portal.interactivebrokers.com/en/pricing/commissions-cryptocurrencies.php?re=europe), and regional exchange schedules linked in Appendix A.

Stock calculations add SEC **$20.60/million sales**, CAT **$0.000003/share each side**; Tiered also includes $0.00020/share/side clearing and commission pass-through factors 0.000175 + 0.00056. TAF is **temporarily zero October–December 2026**. Detailed IBKR fees and its “all-inclusive Fixed” overview conflict; the conservative Fixed scenario keeps SEC/CAT separate without adding Tiered venue/clearing costs. [SEC advisory effective 4 April 2026](https://www.sec.gov/rules-regulations/fee-rate-advisories/2026-2), [TAF holiday filing](https://www.govinfo.gov/content/pkg/FR-2026-09-23/html/2026-19392.htm), [IBKR overview](https://www.interactivebrokers.ie/en/pricing/commissions-home.php). Actual route, partial orders, rounding and applicable contract can change totals.

### Cash cost and required gross move

Each cell is **round-trip cash cost in EUR / cost in bp / gross mid-price break-even move in bp**. One bp = 0.01%. Maker rows are commission-only lower bounds; they omit queue risk, adverse selection and unfilled orders.

| Route | €1,000 exposure | €5,000 exposure | €10,000 exposure |
| --- | ---: | ---: | ---: |
| IBKR stock Tiered | 1.02 / 10.21 / **10.22** | 2.56 / 5.12 / **5.12** | 4.55 / 4.55 / **4.55** |
| IBKR stock Fixed | 2.14 / 21.39 / **21.39** | 3.42 / 6.84 / **6.84** | 5.02 / 5.02 / **5.03** |
| Generic share CFD | 2.12 / 21.18 / **21.18** | 3.32 / 6.64 / **6.64** | 4.82 / 4.82 / **4.82** |
| UCITS Tiered, conditional gettex fill | 3.70 / 37.00 / **37.02** | 11.00 / 22.00 / **22.01** | 22.00 / 22.00 / **22.01** |
| UCITS Fixed SMART | 7.20 / 72.00 / **72.04** | 12.00 / 24.00 / **24.01** | 22.00 / 22.00 / **22.01** |
| IBIE spot crypto | 4.20 / 42.00 / **42.09** | 21.00 / 42.00 / **42.09** | 42.00 / 42.00 / **42.09** |
| Coinbase EU taker | 10.60 / 106.00 / **106.56** | 53.00 / 106.00 / **106.56** | 106.00 / 106.00 / **106.56** |
| Coinbase EU maker, fees only | 5.00 / 50.00 / **50.13** | 25.00 / 50.00 / **50.13** | 50.00 / 50.00 / **50.13** |
| Kraken spot taker | 16.60 / 166.00 / **167.39** | 83.00 / 166.00 / **167.39** | 166.00 / 166.00 / **167.39** |
| Kraken spot maker, fees only | 8.00 / 80.00 / **80.32** | 40.00 / 80.00 / **80.32** | 80.00 / 80.00 / **80.32** |
| Kraken derivatives taker, conditional | 1.60 / 16.00 / **16.01** | 8.00 / 16.00 / **16.01** | 16.00 / 16.00 / **16.01** |

Reproduction: for exposure `N`, adverse half-round-trip price factor `a`, per-side percentage fee `f`, crypto flat-market cash cost is `N*(2*a+2*f)` and exact break-even is `(1+a)*(1+f)/((1-a)*(1-f))-1`. Stocks with absolute round-trip fees `F` and sell-only SEC rate `k` use cash cost `N*(2*a+k*(1-a))+F` and break-even `((1+a)+F/N)/((1-a)*(1-k))-1`. This explains why percentage-fee break-even slightly exceeds flat-market cash-cost bp. Calculations use decimal arithmetic; table rounding is presentation only.

**Binance fees are intentionally not assigned a Romanian execution default.** Once the legal product/entity and account tier are confirmed, insert its current spot or derivative maker/taker schedule into the same calculation. Public archive availability and global/promotional fee headlines cannot establish that executable fee.

### Futures: whole contracts

Hypothetical underlying levels: S&P 500 **6,000**, BTC **$100,000**, ETH **$3,000**. Base friction is two ticks total per round trip (one full spread plus half a tick slippage/side). Margin is collateral, not maximum loss.

| Contract | One-contract exposure USD / EUR | Tick value | Published fees RT | Base total USD / EUR | Gross break-even | Contracts at/below €1k / €5k / €10k exposure |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| MES: $5 × index | 30,000 / 27,272.73 | $1.25 | $1.22 | 3.72 / 3.38 | **1.24 bp**, 0.744 index points before tick rounding | **0 / 0 / 0** |
| MBT: 0.1 BTC | 10,000 / 9,090.91 | $0.50 | $4.02 | 5.02 / 4.56 | **5.02 bp**, $50.20/BTC before rounding | **0 / 0 / 1** |
| MET: 0.1 ETH | 300 / 272.73 | $0.05 | $0.62 | 0.72 / 0.65 | **24.00 bp**, $7.20/ETH before rounding | **3 / 18 / 36** |

Contract sizes/ticks: [MES](https://www.cmegroup.com/markets/equities/sp/micro-e-mini-sandp-500.contractSpecs.html), [MBT](https://www.cmegroup.com/markets/cryptocurrencies/bitcoin/micro-bitcoin/specs), [MET](https://www.cmegroup.com/markets/cryptocurrencies/ether/micro-ether/specs).

Fee decomposition/side: MES **0.25+0.35+0.01**, MBT **0.85+1.15+0.01**, MET **0.20+0.10+0.01** (broker + exchange + regulatory). [IBIE futures](https://www.interactivebrokers.ie/en/pricing/commissions-futures.php), [CME charges](https://www.interactivebrokers.ie/en/accounts/fees/CME.php). A four-tick stress gives $6.22 / $6.02 / $0.82 respectively. Additional rolls incur their own orders/friction; a flat daily strategy does not automatically incur an overnight roll trade.

One coherent **indicative** IBIE Europe/risk-based margin-page snapshot retrieved 30 October: MES intraday initial **$1,928.94**, long overnight initial/maintenance **$2,755.625/$2,197.39**; MBT overnight **$3,349.08/$2,870.64**; MET long **$106.518/$92.6242**, short **$127.821/$111.149**. Other cached locale/query pages differ; these are not account quotes. Intraday relief ends before the regular-session close, which matters to ITSM's closing window. [Exact margin query](https://www.interactivebrokers.ie/en/trading/margin-futures-fops.php?ex=us&hm=eu&pm=0&rgt=0&rsk=1&rst=040404040404040104). Actual capital and safety buffers remain unspecified.

### Other costs that change the decision

- **FX:** manual 0.20 bp, $2 minimum; auto approximately 3 bp per actual conversion. Two conversions add ~6 bp automatically or manual minimums €3.64 total. Prefunded USD amortizes conversion; EUR base currency does not imply conversion on every trade. [FX schedule](https://www.interactivebrokers.ie/en/pricing/commissions-spot-currencies.php).
- **Borrow/carry:** no actual borrow availability/rate checked. Ordinary same-day borrow may be zero, with exceptions. Hypothetical 5%/50% annual borrow on 102% collateral/360 adds 1.42/14.17 bp per charged day. Share-CFD retail long financing is illustrative 6.38% after the extra retail spread (~1.77 bp/charged day); exact cutoff matters. [Short costs](https://www.interactivebrokers.ie/en/pricing/short-sale-cost.php), [pre-borrow](https://www.ibkrguides.com/traderworkstation/about-pre-borrows.htm), [CFD financing](https://www.interactivebrokers.ie/en/trading/ibkr-share-cfds.php).
- **Funding:** hypothetical 1 bp/hour adds 0.083/0.25/0.50 bp over 5/15/30 minutes if continuously accrued. Apply actual product rules. [Kraken examples](https://support.mtf.kraken.com/hc/en-us/articles/29694821654685-Funding-Rate-Examples).
- **Live data:** IBKR nonprofessional tapes A/B/C L1 currently $1.50 each/month; CME L1 $1.55. Alpaca consolidated live plan $99/month, free IEX separate. Subscription does not establish archive rights. [IBIE data](https://www.interactivebrokers.ie/en/pricing/market-data-pricing.php), [Alpaca plans](https://docs.alpaca.markets/us/docs/about-market-data-api).
- **Infrastructure/transfers:** existing local hardware suffices for initial research; no mandatory VPS/colocation. Funding/withdrawal charges are not per-trade fees: Alpaca's US retail schedule lists international outgoing wire $35 and local-currency transfer 1.5%, capped $40; applicability to Romania remains unresolved. [Schedule revised 12 October 2026](https://files.alpaca.markets/disclosures/library/BrokFeeSched.pdf).

**Volatility is not expected alpha.** Costs create a hurdle, not proof of profitability or universal impossibility.

## Appendix C — free historical data: what is actually established

**Actual tested access: none for every provider below.** No authenticated request or historical file was acquired. “Since 2016” or “all symbols” describes a provider offering, not verified gap-free observations for every chosen instrument.

| Source / instruments | Documented access and workload | Essential semantics / rights / next action |
| --- | --- | --- |
| **Alpaca: SPY, AAPL, NVDA, TSLA, AMD; optional MSFT/AMZN** | Basic $0; historical SIP older than 15 minutes, history since 2016; authenticated key, 200 requests/minute; 10,000 **total** records/page across symbols, follow every `next_page_token` | Keep raw historical dollars/shares for ticks and fees; separate explicit split-adjusted return view. Bar labels are interval starts. `asof` controls symbol mapping, not a point-in-time adjustment vintage. Confirm applicable data-only agreement and archival rights. |
| **IBKR: same stocks/SPY** | Account/entitlement-dependent; minute history technically supported, exact six-year coverage untested. Small-bar six-month/60-per-ten-minute restrictions refer to bars **≤30 seconds**, not 1m | Filtered/revised history may differ from live. TRADES split-adjusted; ADJUSTED_LAST also dividend-adjusted with request constraints. Streaming entitlement and GFIS/API/non-display terms matter. Not the first free archive choice. |
| **Binance: BTCUSDT, ETHUSDT spot; futures separately** | Public daily/monthly archives, checksums; two pairs × 72 months = **144 monthly files**, plus checksum/metadata work | Earlier spot ms; spot from 2025 μs; do not apply that rule blindly to futures/REST. Pair is USDT, not USD/EUR. Quarantine unexplained gaps; do not invent fills by forward-filling. Personal research terms verified; production restricted as above. |
| **Kraken: XBTUSD/ETHUSD or actual EUR pairs** | Bulk documentation through June 2026 plus incrementals; **five ~2GB parts**, not a tiny archive. REST OHLC only 720 recent entries, including an unfinished current candle | Venue-matched alternative if Kraken execution chosen. No-trade intervals can be absent; absence alone does not identify outage. Exact pair history, units, retention/production rights remain unverified. |
| **Coinbase Exchange BTC-USD/ETH-USD** | Public candles max 300/request; six years = 3,156,480 minute slots, approximately **10,522 requests/symbol**. At 10/s: ~17.5 minutes/symbol rate-budget arithmetic, before latency/retry | Missing/no-trade intervals and incomplete history possible. Advanced is a different endpoint with max 350. Current market-data terms restrict algorithm/AI/ML uses without consent; intended scope needs clarification. |

**Workload, not a speed promise:** six symbols × six years × 252 assumed sessions × 390 minutes ≈ **3.54m RTH bars/~354 full pages**. Including extended hours can mean **8.71m/~871 pages**: roughly 1.8/4.4 minutes of Alpaca rate budget before latency/retries/filtering. Neither Alpaca “2–3 minutes” nor IBKR “2–4 hours” was measured.

Evidence ledger for this table: [Alpaca bars reference](https://docs.alpaca.markets/us/reference/stockbars), [bar/feed FAQ](https://docs.alpaca.markets/us/docs/market-data-faq), [IBKR current limitations](https://www.interactivebrokers.com/docs/tws-api/doc/md/introduction), [historical bars](https://www.interactivebrokers.com/docs/tws-api/doc/md/historical-bars), [Binance schema/checksums](https://github.com/binance/binance-public-data), [Kraken bulk page, updated 12 October 2026](https://support.kraken.com/articles/360047124832-downloadable-historical-ohlcvt-open-high-low-close-volume-trades-data), [Kraken OHLC](https://docs.kraken.com/api-reference/market-data/get-ohlc-data), [Coinbase Exchange candles](https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-product-candles), [Advanced candles](https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/rest-api/public/get-public-product-candles).

**Rights unresolved:** Alpaca's US-resident public terms conflict with global paper/current non-domestic customer documentation; the applicable data-only/supplier agreement was not established. GFIS **1 May 2026** requires non-display consent/API supplement. Coinbase **7 August 2026** terms restrict algorithm/AI/ML uses without consent. Do not infer unlimited archival/production rights, or a blanket ban on all private research. [Alpaca terms](https://files.alpaca.markets/disclosures/library/TermsAndConditions.pdf), [customer agreement §30](https://files.alpaca.markets/disclosures/library/AcctAppMarginAndCustAgmt.pdf), [global paper](https://docs.alpaca.markets/us/docs/paper-trading), [GFIS §4](https://ndcdyn.interactivebrokers.com/Universal/servlet/Registration_v2.formSampleView?formdb=3089), [Coinbase §§2–3](https://www.coinbase.com/legal/market_data). Next action: resolve the governing terms before acquisition/use.

## Appendix D — strategy and implementation assessment

**ITSM has credible research motivation, not demonstrated project profitability.** Gao/Han/Li/Zhou's 2018 study uses SPY 1993–2013; the early return includes **previous close→10:00**, not merely 09:30→10:00. The June 2017 manuscript explicitly contains joint sign agreement using that return and **15:00→15:30**, trading the final half hour. Our strict-negative short rule abstains at zero; its equation (5) uses nonpositive/nonpositive for shorts. Thus the joint rule was not invented here, but instrument, zero handling, delay, fills and costs make our MES experiment an adaptation. [Published record](https://profiles.wustl.edu/en/publications/market-intraday-momentum/), [June 2017 manuscript](https://assets.super.so/e46b77e7-ee08-445e-b43f-4ffd88ae0a0e/files/ee7dac49-530b-4950-b5d0-e0b5eee08f2e.pdf), [project protocol](../experiments/exp001_itsm/README.md).

The often-repeated **6.67%** belongs to the single-signal timing rule; the June 2017 joint-sign result is **4.39%**, including flat days. **6.02%/6.18%** are certainty-equivalent allocation results, not the joint rule's annualized return. The manuscript was read earlier in this audit; its direct PDF now returns 403, with equation/table passages rechecked through indexed source text. Complete final-2018 tables were not independently retrieved. None of these numbers is a project result or a current net-fee forecast. [Publisher introduction](https://www.sciencedirect.com/science/article/pii/S0304405X18301351).

**Earlier illustrative mean-reversion hypothesis (not the active initial task):** a trailing-15-minute return reversal on AAPL, next-available entry, 15-minute exit and long/flat control. A separate VWAP variant must use trailing available VWAP/volume. Compare time-matched/random/no-trade controls; reject apparent alpha that vanishes with bid/ask bounce, delay, costs or frozen validation. Literature supports liquidity/state dependence, not a guaranteed retail edge. [Heston/Korajczyk/Sadka](https://www.bauer.uh.edu/departments/finance/documents/Heston_Korajczyk_Sadka_paper_UH.pdf), [Nagel](https://www.nber.org/papers/w17653).

**Candlesticks:** keep the [existing ten-form definitions/gates](CANDLESTICK_AGENTS.md): freeze thresholds/edges/gaps, use completed available candles, causal confirmations and explicit entries/exits. Neutral Doji/Inside Bar need direction rules. Count every pattern/timeframe/filter trial; treat ambiguous stop/target ordering conservatively. Morphology is not evidence of alpha. [Original negative evidence](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=980583).

**Stock rankings remain unverified.** No primary measured 2020–2025 comparison supports “NVDA best ITSM/AAPL best reversion,” quoted typical spreads/ATR or automatic profitability. Selecting today's winners retains selection bias even when all were listed in 2020. Raw-price/volume and corporate-action fixtures must cover: AAPL 4:1 **2020-08-31**; TSLA 5:1 **2020-08-31**, 3:1 **2022-08-25**; NVDA 4:1 **2021-07-20**, 10:1 **2024-06-10**; AMZN 20:1 **2022-06-06**. AMD's issuer history lists no 2020–2025 split. These are first adjusted-trading dates, not distribution dates. [Apple](https://www.apple.com/newsroom/2020/07/apple-reports-third-quarter-results/), [Tesla 2020](https://ir.tesla.com/press-release/tesla-announces-five-one-stock-split), [Tesla 2022](https://ir.tesla.com/press-release/tesla-announces-three-one-stock-split), [NVIDIA 2021](https://nvidianews.nvidia.com/news/nvidia-announces-four-for-one-stock-split-pending-stockholder-approval-at-annual-meeting-set-for-june-3), [NVIDIA 2024](https://investor.nvidia.com/files/doc_downloads/2024/05/NVIDIA-2024-Stock-Split-FAQ.pdf), [Amazon filing p.3](https://d18rn0p25nwr6d.cloudfront.net/CIK-0001018724/f6c12bbc-aa86-4f1a-8d28-f790dab31a24.pdf), [AMD](https://ir.amd.com/stock-data/stock-split-history).

**Validation:** preserve the settled 2020–2022 / 2023 / 2024–2025 split before fitting; training-only transforms, overlap purging where needed, untouched holdout and all-trial accounting remain mandatory. At one trade/day, ~252 sessions/year means hundreds of opportunities, fewer actual aligned-signal trades—not millions of independent observations. Use dependence-aware uncertainty, cost/delay stress and controls rather than arbitrary CPCV/embargo/paper-day requirements. Keep signal and execution PnL separate. Final revised bars do not prove original receipt time; never fill retrospectively at the signal close or an already-passed next-bar open.

### Code actually inspected and tested

| Area | Finding | Decision |
| --- | --- | --- |
| [Native DBN loader](../src/quantlab/data/databento.py), [catalog/provenance](../src/quantlab/data/store.py) | Actual native definitions/bars decoding; raw IDs/units checked before rounding; hashes, one-to-one provenance, inventory, locks/staging and native round-trip tested | **Keep.** Real vendor definitions/revisions and dated calendars remain unexercised. |
| [Timing](../src/quantlab/time.py), [snapshots](../src/quantlab/data/core.py), [replay](../src/quantlab/data/replay.py) | Open→close shifted exactly once; dispatch uses modeled availability. Snapshot excludes the future outcome and clamps its cutoff; later missing outcomes do not rewrite earlier inputs. Actor submits no orders. | **Keep.** Modeled 1/60-second delays are not measured feed latency or fill validation. |
| [Model](../src/quantlab/data/model.py), normalization/storage | Hardcoded quarterly MES/USD/$5/0.25 tick, integer volume, CME sessions, Databento and synthetic labels | **Change narrowly when authorized.** New assets need true instrument/quantity/calendar metadata and source-specific timestamp mapping; never relabel stock/crypto as MES. |
| [Calendar tests](../tests/test_data_calendar.py) | Spring/fall DST, overnight trade date, cash vs CME closures, early close, roll and expiry cases | **Keep.** Synthetic calendars are not certified 2020–2025 history; fixed Monday roll is project policy, not a universal historical CME convention. |
| Resource bounds | 32MiB compressed/decompressed per file; 100k records/file, 100 chunks/request, 250k decoded bars/dataset before dedup; several materialized lists | **Keep limits.** Six-year archives require bounded partitions, cross-partition previous-session context and global coverage/manifest checks; raising a cap is not a scalability test. |
| Strategies/risk/orders | Conceptual proposals/risk exist in docs; current runtime contains no strategy, fee/fill validation, portfolio/risk execution path or broker activation | **Build only at the authorized rule milestone.** Preserve three families and shared risk; defer ML/LLM, concurrency and live infrastructure. |

Offline IB mapping probe: `BTC/USD.PAXOS` → `CRYPTO/PAXOS`; `BTC/USD.ZEROHASHE` → `STK/SMART` with primary exchange ZEROHASHE. Official current [IB contract docs](https://www.interactivebrokers.com/docs/tws-api/contracts/cryptocurrency) require `CRYPTO/ZEROHASHE` for IBIE. This proves a default-mapping gap, not that every explicit-contract path is impossible. Generic crypto API documents MKT with IOC and LMT with DAY/GTC/IOC (TWS also Minutes), not unrestricted bracket/trailing orders; exact European route support remains untested. [Current order documentation](https://www.interactivebrokers.com/campus/?p=195739&post_type=ibkr-api-page). IBIE advertises 24/7 spot access, subject to outages. CME crypto futures moved to 24/7 in May 2026 with maintenance breaks; do not backcast those hours into 2020–2025. [CME launch confirmation](https://www.cmegroup.com/media-room/press-releases/2026/6/01/cme_group_announceslaunchof247cryptocurrencyfuturesandoptionstra.html).

## Appendix E — Gemini challenge log

Reviewed all [three preserved original reports](research/original/SHA256SUMS.txt) and the latest `GEMINI_REPORT_UNVERIFIED.txt` inside [the handoff](../QUANT_TRADING_AUDIT_HANDOFF.zip). Verdicts below refer to the evidence above; unknown does not mean false.

| Claim | Verdict | Correction / consequence |
| --- | --- | --- |
| Binance offers public historical crypto data | **Verified** | Strong initial research candidate; venue/pair-specific, not every market/order book. |
| All six years are complete; ~12 known gaps can be forward-filled | **Unresolved / overstated** | No archive audit; preserve unknowns and prevent fictitious execution prices. |
| Binance spot changes ms→μs in January 2025 | **Verified** | Preserve typed product/date schema and boundary tests; REST/futures formats differ. |
| Taker-buy columns give OFI and cross-venue correlation >0.996 | **Overstated / unresolved** | They support trade-volume delta/CVD for that venue, not classic order-book OFI including quote changes/cancels. No correlation experiment was reproduced. |
| Alpaca free historical SIP older than 15 minutes | **Verified** | Explicit feed/end; recent SIP denial does not prove silent fallback. Rough volume is not feed certification. |
| Six years in 2–3 minutes and unrestricted retention | **Overstated / unresolved** | Pagination/extended-hours workload and applicable agreements matter. |
| Romanian stocks “100% allowed,” no PDT, all intraday shorts free | **Overstated** | Shares are viable candidates; account, transition regime, borrow and fee exceptions remain. |
| SPY CFD is one-to-one execution and always zero financing | **Overstated / exact contract unresolved** | Separate OTC pricing/fills/PnL; no carry only if genuinely flat before applicable cutoff; short charges can remain. |
| UCITS all close before the target US half-hour | **Contradicted** | Current gettex overlaps; exact IBKR fund/route unverified. Xetra extension alone does not establish IBKR access. |
| IBKR does not offer EU spot crypto (older report) | **Contradicted** | Documented March 2026 launch; updated latest report correctly recognizes it. |
| IBIE spot is long-only | **Verified** | Preserve this correct restriction. |
| Zero IBKR crypto paper support; built-in adapter guarantees API readiness | **Unresolved / overstated** | No product-specific simulator proof; pinned European contract mapping gap verified. |
| MES $0.61/side | **Verified published decomposition** | Preserve it; add spread/slippage, size, FX and margin. |
| MBT and MET universally cost 4–8 bp RT | **Contradicted as a generalization** | Contract notional differs; illustrative MET cost is 24 bp versus MBT 5.02 bp. Micros launched only in 2021, not 2020. |
| Crypto must lose because average volatility is below costs | **Unsupported** | Conditional expected alpha is unmeasured. High costs make a hurdle, not a mathematical proof of all-strategy impossibility. |
| $5 on $5,000 is 1 bp (original report 2 labels) | **Contradicted arithmetic** | It is **10 bp**. Do not preserve the mislabeled spread/slippage assumptions. |
| Full $0.01 stock spread on 100 shares costs $2 RT (original report 3 example) | **Overstated** | From mid prices a one-cent full spread costs **$1 RT** before additional slippage; avoid double counting. |
| Joint ITSM rule earns the cited 6.67%; early return omits overnight | **Contradicted attribution/definition** | Single vs joint timing and certainty-equivalent results differ; keep overnight. The joint sign rule itself exists. |
| Rust/Redis guarantee parity, colocation is mandatory, ML rankings establish the next strategy | **Unsupported** | Current engine work is useful; no architecture/hosting/model expansion is justified by those assertions. |

## Verification and remaining limits

Executed locally on the existing locked environment, without installation or network-enabled tests:

```sh
quantlab_audit_tests=$(mktemp -d /tmp/quantlab-audit-pytest-XXXXXX)
PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -q -p no:cacheprovider --basetemp="$quantlab_audit_tests"
PYTHONDONTWRITEBYTECODE=1 .venv/bin/ruff check --no-cache .
PYTHONDONTWRITEBYTECODE=1 .venv/bin/ruff format --check --no-cache .
PYTHONDONTWRITEBYTECODE=1 .venv/bin/mypy --cache-dir /tmp/quantlab-audit-mypy src/quantlab
```

Results: **120 passed in 6.37s**, **36 upstream Pandas4Warning** messages; lint, formatting and types pass. Original-report checksums pass. These prove the current offline scope, not financial performance, real-feed coverage, brokerage compatibility or server CI execution.

Report checks: local links and whitespace pass; each modeled cost/break-even reconciles to independent entry/exit cash flows. At audit completion, all **53 tracked files**, the handoff archive, Git HEAD/index and all **11 Obsidian Markdown notes** retained their baseline state, and only this report was new. The later authorized scope-alignment task updates planning documents and isolated project memory; it preserves application code, dependencies, original research and Git history. This audit paragraph records historical verification, not a claim that the current worktree is unchanged.

Unresolved items are limited to evidence unavailable without delivered data, applicable agreements or an authorized account review: actual residence/entity/account regime, product permissions/KIDs/short borrow, exact SPY CFD and late UCITS routing, crypto paper/European route behavior, Binance Romanian authorization, account fee tiers, production/retention rights, six-year coverage/fill quality and strategy expectancy. Public sources were checked extensively; blocked final-paper/supplier PDFs and conflicting official terms are identified above rather than treated as verified.

Only this report is intended for review. No approval is requested to make it concrete; approvals concern the subsequent plan/data/account actions listed above.
