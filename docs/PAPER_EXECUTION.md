# Alpaca paper execution

Active choice **2026-10-30**, [D-032](DECISIONS.md): NVDA shares, Alpaca paper at `https://paper-api.alpaca.markets/v2`, free IEX operational data. Historical research remains raw SIP with its original frozen split. The owner authorized credential reuse from InvestorAI and this paper trial. No spending, subscription, live-money route, commit or push is authorized. InvestorAI stays read-only.

## Verified and pending

- The actual paper account returned ACTIVE/USD with trading unblocked, zero positions and zero open orders. NVDA returned active/tradable. Account identifiers and balances are kept out of Git and Obsidian.
- Actual read-only startup **and flat-account restart reconciliation** passed through `AlpacaTransport.refresh()`: cash/position matched the persisted journal, the measured loss field was available and there were no known orders. Thirteen GETs, with order authorization disabled; no broker mutations. This does not verify recovery with actual fills or open positions.
- Explicit `feed=iex` quote access returned HTTP 200. The after-close quote was unusable; fresh in-session quotes remain unverified. No live SIP request or paid fallback occurred.
- The completed-minute reader delivered **780 raw IEX bars**, 390 each on October 29/30, 2026, with no missing cash minutes or forming candles. These current operational sessions are separate from the 2021 SIP pilot and the untouched 2023–2025 validation/holdout prices. No strategy was evaluated on these two sessions.
- The actual `paper-run --max-seconds 1` refused the closed market and queued no order. Alpaca reported the next open as **2026-11-02 14:30 UTC** (09:30 New York; US DST changes before that session).
- Offline recording tests cover ITSM entry → partial fills → timed exit → reconciled flat cash/position, plus lost POST acknowledgement/no resend, duplicate receipts, external activity, wrong account, cancellation ownership and closed-market refusal. **No actual paper order/fill has been verified.**

## Commands

Run from the repository root after the locked installation in [README](../README.md#install-and-check). Credential parsing is literal; the `.env` is never sourced or copied. The first status call saves an isolated paper account binding and conservative numeric simulation limits in ignored `data/alpaca-paper/config.json` (mode 0600): one share, maximum one held share, $1,000 notional/capital ceiling, 1x leverage, $10 daily marked-loss entry halt, one entry attempt/session, ten seconds between orders, 30-second data/state age bounds. These are paper trial limits, not an allocation or calibrated investment risk budget.

```sh
.venv/bin/python -m drift paper-status \
  --credentials-file ~/Documents/finance/investor-ai/.env \
  --authorize-paper-connection

# During a regular session, with operator supervision; stops flat after the time exit.
# Default maximum runtime is seven hours. No weekend/extended-hours order is queued.
.venv/bin/python -m drift paper-run \
  --credentials-file ~/Documents/finance/investor-ai/.env \
  --authorize-paper-connection --authorize-paper-orders

# Persist a halt and request cancellation of this journal's known pending orders.
.venv/bin/python -m drift paper-kill \
  --credentials-file ~/Documents/finance/investor-ai/.env \
  --authorize-paper-connection --authorize-paper-orders
```

`--output PATH` selects a private state directory; retain the same directory on restart. Read its configuration before activation. After a halt, inspect account/journal evidence and add `--resume-paper` only to resume reconciled operation. Resetting/deleting the journal is not recovery. No detached service or scheduled start was installed; a foreground command requires the machine and operator to remain available.

`paper-run` makes one long-only ITSM decision from completed, observed **IEX** minutes at 15:30 New York, within a 30-second entry window; missing/gapped endpoints, stale quotes and disagreement abstain. It fetches at most the previous and current operational sessions, follows pagination and preserves raw units. A large overnight discontinuity abstains pending review; this diagnostic is not complete corporate-action coverage. Entries use the existing rule and proposal contract, then shared portfolio/risk and a fresh quote. The order fills, if any, come from the simulator rather than a candle close. A completed 15:59 minute cannot authorize a fill at its own close.

Time exits begin at 15:58. At most three IOC exit attempts are allowed; stale quotes, unresolved state or an unfilled exit require supervised account resolution. A duration timeout attempts one early exit. Ctrl-C/kill halts and requests cancellation; **it does not liquidate positions**. Polling/process/network failure cannot guarantee flattening. No unattended deployment or strategy acceptance is claimed.

## Implementation and controls

| Module | Boundary |
|---|---|
| `execution/model.py`, `paper.py` | Broker-neutral approved intents, typed policy, durable SQLite reservations/fills, account binding, exclusive writer, long-only sizing/exposure/cash/loss/rate/freshness checks, duplicate prevention and halt. |
| `execution/alpaca.py` | Fixed paper REST host, explicit free IEX reads, raw completed candles, no redirects, bounded reads and body sizes, one mutation attempt, client-order-ID lookup, individual FILL activity pagination and account/order/position/cash reconciliation. |
| `execution/alpaca_cli.py` | Private configuration/status, bounded supervised ITSM runner, time exits and halt command. |
| `execution/ibkr.py`, `nautilus.py`, `runtime.py` | Earlier, inactive IBKR/Nautilus bridge and offline regression evidence; not selected or connected by Alpaca commands. |

Persist PREPARED before transport and SENDING before the wire call. Recheck account identity, expiry and broker clock before sending. Only whole-share NVDA limit IOC orders in regular hours are supported; the adapter supplies no alternate host or live toggle. Unknown submissions reserve exposure and never resend automatically. A lookup by stable `client_order_id` and complete receipts are required for recovery; a missing open order is not cancellation proof. Cancellations must match a journal-owned broker order.

Cash, positions, known order states and cumulative fills must reconcile. Individual fill activity IDs/prices/quantities populate the ledger; order averages never manufacture executions. Repeated receipts are idempotent; missing/conflicting receipts or external orders/positions halt. Account `last_equity - equity`, floored at zero, supplies a conservative marked daily loss measure; unavailable values block operation. Transfers, dividends, corporate actions or external activity are not silently adopted. Historical orders/fills are reread within a bounded request budget; this is a small supervised trial, not an archive-scale or multiday execution service.

Private state: `data/alpaca-paper/config.json`, `status.json`, `receipts.jsonl`, `iex-check.json`, `reconciliation-check.json`, `events.jsonl`, `paper.sqlite` and its lock. Receipts include private account responses and raw IEX results, without request authentication headers or error bodies. Protect this directory; publish none of it. Preserve the separate `data/alpaca-pilot/` historical provenance.

## Verification and limits

```sh
.venv/bin/ruff format --check .
.venv/bin/ruff check .
.venv/bin/mypy
.venv/bin/pytest -q
```

Full verification on 2026-10-30: **428 tests passed** (18 Alpaca paper tests), Ruff format/lint, strict mypy, locked offline dependency checks, 181 local Markdown links and original research checksums passed. The 236 warnings are upstream Nautilus/pandas deprecations. Tests are socket-disabled and synthetic; actual read-only verification is recorded separately above. Existing IBKR native-node tests permit only the local AF_UNIX asyncio wakeup pair while Internet sockets stay blocked. No new dependency or service is needed for Alpaca REST.

The [official paper guide](https://docs.alpaca.markets/us/docs/paper-trading), [data plans](https://docs.alpaca.markets/us/docs/about-market-data-api), [orders](https://docs.alpaca.markets/us/docs/orders-at-alpaca), [order submission](https://docs.alpaca.markets/us/reference/postorder), [client-ID lookup](https://docs.alpaca.markets/us/reference/getorderbyclientorderid), [fill activities](https://docs.alpaca.markets/us/docs/account-activities) and [bars](https://docs.alpaca.markets/us/reference/stockbars) were checked on 2026-10-30. Paper fills are simulations against NBBO, even when observations use IEX. Paper does not model all latency/queue/impact or regulatory fees. Recorded paper fill fees use **zero as the documented simulation assumption**, not verified real trading cost. Cash discrepancies still halt. Historical research retains explicit cost scenarios.

Full SIP admission, effective corporate-action/retention evidence, evaluated historical strategy performance, usable live-session quotes and actual paper order/fill/restart scenarios remain incomplete. The IEX operational trial is expressly separate from promotion of the SIP research candidate. Live money remains outside scope.
