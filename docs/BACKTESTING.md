# Backtesting framework

Run any selection of strategies over a chosen window, concurrently, and keep complete, queryable results. Virtual portfolios add accounts that persist across runs. Everything here is simulation: no module in `research/` can reach a broker, and these accounts are unrelated to Alpaca paper accounts. Fill timing and strategy rules live in [D-030](DECISIONS.md) and [STRATEGIES.md](STRATEGIES.md); the archive in [NVDA_HISTORY.md](data/NVDA_HISTORY.md).

## Commands

```sh
drift research strategies                               # what is registered
drift research run --year 2020                          # every strategy, concurrently, $20,000 each
drift research run --start 2021-03-01 --end 2021-06-30 --strategies itsm,orb
drift research run --year 2021 --capital 50000 --costs stressed --workers 2
drift research run --year 2021 --sequential             # in this process, for a debugger
drift research run --year 2021 --timeout-seconds 600    # stop a hung strategy
drift research run --year 2021 \
  --set execution.slippage_bps=3 --set orb.params.horizon_seconds=900 --settings tuned.json
drift research compare --sort sharpe                    # the latest batch; --batch ID, --json
drift research show RUN_ID                              # a run's full manifest

drift portfolio create steady --strategy itsm --capital 20000
drift portfolio advance steady --start 2020-01-02 --end 2020-06-30
drift portfolio advance steady --end 2020-12-31         # continues where it stopped
drift portfolio configure steady --set params.allow_short=true
drift portfolio advance steady another --year 2021      # several, concurrently
drift portfolio list
drift portfolio show steady
```

Results go to `data/research/` (`--store`), which Git ignores. `--source synthetic` runs on seeded candles with no archive. A run exits 1 if any strategy failed, after storing the others, and 2 on invalid input.

## Research split

`scope.authorize` runs before any data is read, and the engine repeats the check on what it actually trades.

| Window | Behavior |
|---|---|
| Development 2020–2022 | Open |
| Validation 2023 | Refused unless `--allow-validation`; each run records `research_role`, so looks are countable in `runs` |
| Holdout 2024–2025 | Refused, with no override. Using it needs a reviewed decision and a code change |

Development results are in-sample, and defaults are untuned. Every attempt, including failures, is logged in `batches` before it runs, so trial counts stay honest: a `started` row marks an attempt that was interrupted.

## Settings and costs

Defaults live only in `research/settings.py`: $20,000, long-only (no borrow availability or rate is verified), and 95% of the current balance per trade. Risk limits scale with `--capital`. `--set` and `--settings` share one rule: `section.key=value` applies to every selected strategy and `strategy.section.key=value` to one, where a section is `execution`, `sizing`, `risk`, `params` or `exit`. Decimals stay exact text. Unknown paths are refused.

Costs are a named profile, recorded on each run (`custom` once overridden), so a run cannot silently have none.

| Profile | Half-spread + slippage, each way | Commission | Sell fee | Latency |
|---|---|---|---|---|
| `zero` | none, an arithmetic baseline | none | none | 0 |
| `base` (default) | 1 + 1 bps of the bar open | $0.0035/share, $0.35 minimum, 1% cap | 0.00206% | 0 |
| `stressed` | 3 + 3 bps | $0.005/share, $1 minimum, 1% cap | 0.00206% | 30 s |

Spread and slippage are assumptions: the archive holds no quotes. They are in basis points because a fixed tick is a very different cost at a raw $750 and a raw $150. Commissions are the [documented reference inputs](COSTS_AND_PROVIDERS.md#nvda-execution-costs-and-units), not an era-specific schedule. Fixed-tick costs remain available through `execution.half_spread_ticks` and `execution.slippage_ticks`.

## Concurrency and isolation

NautilusTrader 1.231.0 [does not support](https://github.com/nautechsystems/nautilus_trader/blob/v1.231.0/docs/concepts/architecture.md) concurrent engines in one process, so each strategy gets its own spawned process, with at most `--workers` alive (default: up to 4, measured at 1.3 GB each on the three-year window). A process per job rather than a pool: a pool breaks as a whole when one worker dies, and that must cost only that strategy. Exceptions, crashes and timeouts become recorded failures; the others finish and are stored. Each job builds its own agent, engine and account, so results cannot depend on scheduling: tests hold sequential and concurrent runs to identical hashes.

Verification is split so a batch stays fast. The parent replays each touched month from its raw receipts once; workers read hash-checked Parquet.

## Results

Each run is an immutable directory, `runs/<run_id>/`, published atomically: Parquet tables plus a manifest. `run_id` hashes everything that can change an outcome (kind, strategy, window, portfolio position, resolved configuration, candles, and code: package source, engine, Python and plugins), so it names the experiment. Repeating a run reuses it, and if the repeat disagrees the run is refused as non-reproducible. `results_sha256` hashes the outcomes without ids. Wall-clock time appears only in `batches` and portfolio records, and `batches` is the only file rewritten in place.

```python
from pathlib import Path
from drift.research.store import ResultStore

with ResultStore(Path("data/research")).connect() as db:
    db.sql(
        "SELECT strategy, net_pnl, sharpe, max_drawdown_pct, trades_per_session "
        "FROM comparison ORDER BY sharpe DESC"
    ).show()
```

| View | Rows |
|---|---|
| `runs` | One per run: strategy, family, kind, window, research role, cost profile, config/data/code/result hashes, `config_json` |
| `trades` | Entry/exit times and prices, quantity, gross, fees, net, exit reason, signal, proposal |
| `orders`, `fills` | Every order with its status; every fill with its price and commission |
| `equity` | One per bar: cash, signed position, mark, equity, high-water mark, drawdown |
| `proposals` | Every proposal and what became of it |
| `metrics`, `comparison` | Long form, and one wide row per run for ranking on profit, risk and frequency |
| `batches` | Every attempt, with its status, errors and tracebacks |
| `portfolios`, `portfolio_configs`, `portfolio_segments`, `portfolio_trades`, `portfolio_equity` | Identities, configuration history, and only what was committed to a portfolio |

A dashboard has two options, both read-only: call `connect()`, or point any DuckDB client at the same globs, such as `read_parquet('data/research/runs/*/trades.parquet', union_by_name=true)`. Files in `runs/_schema/` and `portfolios/_schema/` are empty on purpose, so a glob always matches with the right types.

Equity marks open positions at each bar's close, so drawdown and Sharpe see losses that realized PnL hides. Cash is the engine's balance, which books each fill in whole cents; trade PnL is exact, so `sum(net_pnl)` can differ from final cash by up to a cent per fill (at most $0.22 over 1,907 trades in 2020).

## Virtual portfolios

A portfolio binds one strategy to its own capital, a versioned configuration and a chain of segments. An independent experiment (`research run`) has none of these and never appears in the `portfolio_*` views.

**Continuation replays instead of restoring.** Agents receive no feedback from execution, so an agent's state is a pure function of its parameters and the candles it has seen. A new segment therefore starts a fresh agent, replays every candle since the portfolio's first day through the same engine path with no quotes and no decisions, and trades only the new window. Cash, the high-water mark and the trade count carry over; session counters reset at the boundary anyway. This needs no strategy-specific serialization, so it works for any replayable strategy. Replay time grows with the history: advancing one session after three years took 26 s, including verification.

The guarantee is that a segmented portfolio equals one uninterrupted run, trade for trade and metric for metric. Tests hold every strategy to that, and it was confirmed on the real development archive for all seven strategies then present (including the since-removed candlestick rule): 2020–2022 in four segments, with one boundary on the 2021 split. A segment is refused rather than approximated when the guarantee would not hold:

| Condition | Why |
|---|---|
| The account ended with an open position | Nautilus cannot be seeded with a position; closing it would invent a trade |
| An order could still be live at the next open | It would fill in an uninterrupted run, and be lost here |
| The strategy is not `replayable` | A future LLM agent may not be a pure function of its inputs |
| Market history differs from what the last segment saw | The replayed state would be a different agent |
| Code changed since the last segment | Replay may not reproduce the past; `--accept-code-change` proceeds and records it |

Continuity needs no check: a continuation takes only an end date, and its start is derived from the last session, so a gap or overlap cannot be requested. Committing is one atomic file creation, so two racing runs commit at most once, and a crash between publishing and committing is repaired by running the same segment again.

`portfolio configure` adds a settings version effective from the next segment; earlier versions stay in `portfolio_configs`. A changed parameter replays history under its new value, as if the agent had always held it, without rewriting any past trade. Capital is fixed at creation.

## Extending

| To add | Change |
|---|---|
| A strategy, of any family | One `register(StrategyEntry(...))` call: `parse` validates parameters, `make` builds the agent, and `replayable` and `split_safe` state what it can promise. Built-ins sit in `backtest/config.py`; a module outside the package loads with `--plugin module`, and its source hash joins the run's code version. The runner needs no change |
| A data source | An adapter with `historical`, `verify` and `load` ([sources.py](../src/drift/research/sources.py)), wired into `_market` in the CLI |
| A metric | One `@metric` function in [metrics.py](../src/drift/research/metrics.py); it reaches `metrics` and `comparison` with no schema change |
| An instrument | Instrument metadata, per the [extension interfaces](ARCHITECTURE.md#extension-interfaces) |

| Module (`src/drift/research/`) | Owns |
|---|---|
| `scope` | Windows and the research-split gate |
| `sources` | Market data adapters: refuse gaps, never fill them |
| `settings` | Defaults, cost profiles, overrides, resolved configuration |
| `runner` | One job (`execute`), failure containment (`attempt`), a batch (`run_batch`) |
| `executors` | Sequential and process execution |
| `records` | Mapping an engine result to stored tables and ids |
| `metrics` | Comparable metrics, shared by runs and portfolios |
| `store` | Immutable Parquet and DuckDB views |
| `portfolios` | Identity, configuration history, continuation and its guards |
| `cli` | Argument handling only |

## Limitations

- **Fills are bar-open proxies, not NBBO.** Queue position, partial fills and market impact are unmodeled; 95% of $20,000 is small against NVDA's volume, but a large `--capital` needs a liquidity check first.
- **Stops and targets read bar highs and lows,** and the archive contains isolated wicks that look like late prints (9 bars above 1% in development; 2022-01-26 is the clearest case). Stop-based results may be affected; closes are not.
- **A short window starts cold.** ITSM abstains on a run's first session, as lookback filters do until warm. Nothing substitutes for the missing history; portfolios avoid this by replaying.
- **Raw prices cross splits.** A window containing a split refuses any position that could cross it, and any configuration that compares raw prices or volumes across sessions: ORB's `rvol_min` and `prior_tr_below_atr`. A strategy claims `split_safe` in its registry entry; plugins are refused until they do. ITSM is safe because the runner passes it the reviewed splits. Such a configuration can run on windows without a split, such as 2020 or 2022.
- **Missing minutes stay missing.** Orders wait for the next real bar, and rules abstain. Counts are on each run (`missing_minutes`).
- **Reversal is costly by construction:** at up to 8 trades a session it pays the assumed costs thousands of times, so its results mainly measure the cost assumption.
- **Metrics describe a sample.** `sharpe_standard_error` assumes i.i.d. returns, and nothing here corrects for the number of trials.
- **Replay time grows with history,** and intervals are whole days, so a portfolio cannot stop mid-session.
