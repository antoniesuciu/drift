# M2b.2 — vendor pricing and rights verification

Reviewed **2026-10-29**, using public first-party documentation, the official Databento API reference and Context7. No account login, authenticated metadata query, data/sample download, purchase or vendor contact occurred. This note updates the procurement evidence in [PROVIDER_COMPARISON.md](PROVIDER_COMPARISON.md); dataset selection remains [MES-ITSM-DATA-v1](HISTORICAL_DATA_SPEC.md). **Public price structure is verified; request-specific totals and applicable Databento retention terms are not.**

## Costs that can and cannot be established publicly

| Purchase under consideration | Verified amount on this review | Disposition |
|---|---|---|
| Databento March pilot, including preceding close and roll overlap | **Unquoted**, not USD 0 | Exact dated-contract request estimate required. |
| Databento November pilot, including preceding close | **Unquoted**, not USD 0 | Separate estimate required; do not extrapolate from March. |
| Databento complete 2020–2025 archive, 25 expiry months | **Unquoted**, not USD 0 | Estimate each selected contract/window/schema and sum; retain overlap in the quote. |
| Databento CME Standard plan | **USD 199/month**, publicly advertised | Optional alternative to PAYG; not selected or necessary for this preparation. |
| FirstRate individual MES purchase | **Unquoted** in the accessible product page | Obtain the location-specific Buy Now price before selecting it. |
| FirstRate MES updates after the included first month | **USD 99.95/year**, advertised | Optional updates, not the initial archive purchase price. |

Databento advertises historical usage-based access without a subscription. Its Standard plan includes over 16 years of L0 history, explicitly including OHLCV, definitions and status; compare that option against the exact PAYG total if economical, subject to account eligibility and cancellation/retention terms. Neither an empty calculator's sub-cent display nor the live-plan price establishes this project's archive cost. [Databento pricing](https://databento.com/pricing).

Historical PAYG is metered on uncompressed binary bytes; CSV/JSON conversion and normal HTTP/FTP delivery do not add usage charges. Batch requests are billed once and their results can be downloaded again for 30 days; this is a delivery window, not a retention license. New-user credits are advertised at USD 125, shared once per team and expiring after six months. Eligibility and remaining balance are unknown, so the acquisition budget must show gross cost before any credits. [Pricing and credits FAQ](https://databento.com/docs/faqs/usage-pricing-and-data-credits).

The catalog's monthly calculator uses the previous 30 days of data sizes. It cannot establish 2022 or six-year MES charges by multiplication. [Data catalog guide](https://databento.com/docs/portal/data-catalog). No public minimum purchase amount or project-specific tax/FX/payment charge was established here; absence of a displayed minimum is not a zero-fee guarantee.

FirstRate describes dataset purchases as one-off, with no automatic rebilling and one month of included updates. Its FAQ says the Buy Now price is localized, includes applicable tax, and varies by location; a USD figure is indicative. It does not offer custom shorter-history orders. Thus a recent free sample or a request for just two pilot windows is not its purchase model. Single-ticker purchases use private download pages rather than the bundle API. [Purchasing/delivery FAQ](https://firstratedata.com/about/FAQ), [MES product and update price](https://firstratedata.com/i/futures/MES). No sample link was opened.

## Quote procedure after account-owner authorization

Use the actual plan's allow-listed dated outright contracts and half-open UTC bounds. March envelope: `[2022-03-04T00:00:00Z, 2022-03-26T00:00:00Z)`; November: `[2022-11-18T00:00:00Z, 2022-12-03T00:00:00Z)`; archive envelope: `[2019-12-30T00:00:00Z, 2026-01-01T00:00:00Z)`. These envelopes are **not** instructions to request every pilot contract for every date or an entire parent product. Quote the contract-specific intersections and required definition snapshots separately.

The historical API requires authentication. `metadata.list_unit_prices` supplies schema/feed-mode USD/GB rates; `get_record_count`, `get_billable_size` and `get_cost` accept a matching dataset/symbol/schema/time selection. Metadata and symbology calls are documented as free; definition/status records obtained through time-series methods are data requests, not automatically free metadata. Estimates can over-report on ranges not aligned to ten-minute multiples; definitions require 24-hour multiples for accurate estimates. Actual billed bytes govern the final charge. Explicitly set `dataset=GLBX.MDP3`, `schema`, `symbols`, `stype_in` and both bounds: omitted symbols can select all symbols and the default schema is trades. No estimator was called here. [Historical API, metering and metadata methods](https://databento.com/docs/api-historical).

For each proposed request, the account owner should save a sanitized quote record containing request ID/hash, exact symbol/ID mapping, bounds, schema, record count, billable bytes, unit price/mode, gross USD estimate, any verified discount/credit, tax/FX treatment and observation date. Record uncertainties and a user-approved maximum per job and for the complete pilot. Sum bars, definitions and any separately justified status request; keep optional trade/BBO evidence out of the initial bill. Compare the archive quote independently with one month of eligible Standard access and FirstRate's actual offer. No quote is a permission to submit a job.

The billing portal supports a historical monthly spending limit; without one the account is unlimited. The documentation says requests are blocked after monthly usage exceeds the limit, so use that account control together with pre-request cost checks rather than assume a strict per-request atomic budget cap. [Billing guide](https://databento.com/docs/portal/billing).

## Rights: evidence and open conditions

Databento's historical service guide states there are no monthly license fees. Its licensing explanation says ordinary historical access generally does not require the real-time exchange licensing process, while redistribution is an exception. **This does not establish perpetual use or ownership of purchased CME files.** A new live subscriber license must not be imposed merely because this project is buying old data; the actual historical terms and permitted use must instead be identified. [Service distinction](https://databento.com/docs/quickstart/choose-service), [Databento licensing explanation](https://databento.com/blog/introduction-market-data-licensing).

| Intended Databento/CME use | Public evidence | Required disposition before acquisition |
|---|---|---|
| Private research and local raw DBN / normalized Parquet | Historical file delivery is documented; no reviewed contract explicitly settles all storage/use terms. | Obtain the terms applicable to this account, dataset and use, including format conversion and repeated local replay. |
| Backups, second machine, third-party hosting/processors | No sufficiently specific public permission verified. | Confirm allowed copies, access boundaries and processor restrictions; keep the first acquisition local pending approval. |
| Retention after PAYG inactivity, subscription cancellation or account termination | Not verified from accessible terms. | Written terms/confirmation must say whether raw, curated and backup copies can remain and for how long. The 30-day redownload window does not answer this. |
| Internal statistical/model research and later non-reconstructive derived outputs | Generic marketing does not settle this use's complete rights. | Confirm internal research/model use and whether publishing statistics/models/reports is allowed; no external LLM upload is authorized. |
| Raw data, bars, downloadable charts or API redistribution | CME imposes historical distribution controls. | Keep private. Any future distribution needs a separate rights review and authorization. |

The public [Databento terms entry point](https://databento.com/legal) yielded an application shell without reviewable substantive terms in this session. Searches did not establish an applicable perpetual-retention clause. This is an **evidence gap**, not a finding that storage is forbidden. Obtain the current agreement/version and applicable publisher terms from the account owner, or authorized vendor clarification, without copying confidential agreements or account details into Git/Obsidian.

CME's September 2024 historical-distribution guidelines define historical information as first accessed at least eight hours after transmission and require historical distribution licensing, including for public chart/tabular display. Download/export/API availability has additional subscriber-feed implications. These are distribution rules, not proof that this private research project owes a distributor fee or must delete its archive. They also prevent treating Databento's generic “most datasets” redistribution statement as CME permission. [CME historical information distribution policy](https://www.cmegroup.com/market-data/distributor/files/cme-group-data-licensing-policy-guidelines-historical-information-distribution.pdf).

FirstRate's public license is clearer on retained local research: it grants a perpetual license, permits own-server storage, database import and derivative works, and describes service-provider hosting and purchased multi-user permissions. It restricts raw-data redistribution/commercial resale; published research/analysis should attribute FirstRate under the full agreement. The FAQ says attribution is merely appreciated, so follow the **full license's stricter attribution wording** unless clarified. Retain the reviewed license version with the purchase evidence. Perpetual use survives the update subscription, while download access can expire. Neither its license nor marketing verifies delivered coverage/quality. [Full license](https://firstratedata.com/about/license), [FAQ on expired subscriptions](https://firstratedata.com/about/FAQ).

## Acquisition decision still required

Recommended sequence: account-owner quote/terms review first, then select the cheaper suitable verified offer, approve a numeric pilot ceiling and rights summary, resolve the implementation/calendar prerequisites in the acquisition plan, and only then seek explicit permission to submit the bounded pilot jobs. **No acquisition is authorized by this note.** Gates 013/014 remain pending delivered artifacts and validation, even if a quote is affordable or credits cover it.

The evidence request is specific: (1) March, November and archive quote records, including metadata/status costs; (2) applicable Databento/CME local/backup/research/post-termination/derived-use terms; (3) FirstRate's tax-inclusive local initial MES purchase price if it remains competitive; (4) the approved provider, total ceiling and retry policy. No credentials are requested in chat, and no vendor contact was made.
