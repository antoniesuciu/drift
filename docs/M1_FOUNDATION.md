# M1 — verified offline foundation

Validated 2026-10-29. Scope: [TASK_M1.md](../TASK_M1.md), [M1 roadmap](ROADMAP.md#m1--project-foundation), REQ-DATA-002's M1 timing cases, REQ-BACKTEST-001, REQ-NFR-001/002 and the M1 CI secret-check configuration in REQ-SEC-001. No M2 ingestion, strategies, orders, broker connection, training or paid data was introduced.

## Environment and dependency decision

| Item | Verified selection |
|---|---|
| Local platform | Ubuntu 24.04.5 LTS, Linux x86_64 |
| Interpreter | CPython 3.12.3; supported package range `>=3.12,<3.13` |
| Resolver/installer | uv 0.13.6, required by project configuration |
| Package/build | `quantlab` 0.1.0, src layout, Hatchling 1.33.0 |
| Engine | Stable PyPI NautilusTrader 1.231.0, CPython 3.12 manylinux_2_35_x86_64 wheel |
| Optional integration import dependencies | `nautilus-trader[ib]`, nautilus-ibapi 10.45.1, protobuf 5.29.6; no Docker extra |
| Quality | pytest 9.2.0, pytest-socket 0.8.1, Ruff 0.17.3, mypy 1.20.2 |
| Relevant transitive data dependency | pandas 3.1.0 (locked, not an ingestion implementation) |

`uv.lock` pins transitive versions and distribution hashes. Tool constraints in `pyproject.toml` permit reviewed upgrades only through an explicit lock update; CI uses `--locked`. Build backend is separately pinned. Python patch/OS image is not locked by uv; the local patch above is the verified tuple, while CI targets the same minor line. Upgrade to supported patch releases and rerun gates; no success on untested platforms is implied.

The [official release metadata](https://pypi.org/project/nautilus_trader/1.231.0/) and [tagged project metadata](https://github.com/nautechsystems/nautilus_trader/blob/v1.231.0/pyproject.toml) support this interpreter/wheel and optional IB dependency selection. Context7 was queried against `/nautechsystems/nautilus_trader/v1.231.0`; moving `latest` 2.x examples were not used. No framework replacement was necessary. Dependency provisioning required network; fresh-environment replay/tests then succeeded offline using the populated local cache.

## Actual APIs and boundaries

The implementation uses `BacktestEngine`, `BacktestEngineConfig`, `LoggingConfig`, `FuturesContract`, `BarType`, `Bar`, `Actor`, simulated venue registration, `add_instrument`, `add_actor`, `add_data`, `run`, `get_result` and `dispose`. The observer subscribes to bars and records callbacks and the engine clock; it contains no trading policy or order submission. A fresh engine is disposed after every run.

The fixture is MESZ6.CME with synthetic activation/expiry metadata, USD 5 multiplier and 0.25-point tick, plus three completed minute bars starting 2026-03-09 13:30 UTC. Values/volume/contract dates/account balance are synthetic; contract permissions, margin and tradeability have not been established. `ts_event` denotes interval completion in this fixture; `ts_init` denotes completion plus configured delivery delay. The selected engine sorts and dispatches data by `ts_init`. Callback observations demonstrate bars are not delivered at their start or before modeled availability. Vendor timestamp mapping and exchange calendars remain M2.

`BarInterval` validates aware datetimes, normalizes to UTC before comparing instants (including DST folds), rejects imaginary local times, nonpositive windows and availability before completion. `SmokeConfig` bounds fixture size and latency. These are the only shared foundational types needed now. The conceptual proposal schema remains in [AGENT_ARCHITECTURE.md](AGENT_ARCHITECTURE.md#proposal-contract) for M3; no agent skeletons, broker wrappers, portfolio/risk implementations or orchestrators were created.

Historical API references: [tagged backtest API](https://github.com/nautechsystems/nautilus_trader/blob/v1.231.0/docs/api_reference/backtest.md), [data semantics](https://github.com/nautechsystems/nautilus_trader/blob/v1.231.0/docs/concepts/data/index.md), and the installed release's `backtest/engine.pyx` and native object docstrings. These references were checked alongside the running installed wheel rather than assumed interchangeable with 2.x.

## Future IB compatibility, bounded evidence

The release's `interactive_brokers.config`, `data`, `execution` and `factories` modules import under socket-blocked pytest with the optional `ib` extra installed. No client, `TradingNode`, credential loader, TWS/Gateway process or live data/execution factory is instantiated by this application. The CLI exposes only `smoke`, plus standard help/version; paper/live/connect/download commands are rejected.

The [tagged IB guide](https://github.com/nautechsystems/nautilus_trader/blob/v1.231.0/docs/integrations/ib.md) documents TWS/Gateway, historical/streaming requests, execution, UTC timestamp configuration and the separate optional Docker integration. This pinned 1.x adapter uses the packaged IB API dependency; the moving 2.x Rust transport notes in M0's provider review do not define this release's transport. There is no Docker dependency or gateway deployment in M1. Account/server handshake, entitlements, historical depth, paper identity, reconnects, reconciliation and executable safety remain unverified and separately authorized M2/M6 work. Import success does not establish operational brokerage compatibility.

## Verification and limitations

| Gate | Evidence |
|---|---|
| Installable/reproducible package | Locked editable install, independent fresh offline environment, source/wheel build and separate non-editable install; package metadata and console entry point verified. |
| Functional tests | 36 passing pytest cases with `--disable-socket`: package/CLI, rejected network/order modes, config boundaries, actual engine replay, zero orders/positions, configured fixture sizes/latencies, IB module imports, completion/availability, UTC/ET DST transitions/fold, nonexistent/naive time and invalid intervals. |
| Determinism | Equal reports from fresh engines in tests and byte-identical JSON from independent CLI processes; event times/closes/callback clocks and engine iteration counts are checked. Wall-clock durations and random run IDs are intentionally excluded, not claimed deterministic. |
| Quality | `ruff format --check .`, `ruff check .`, strict source `mypy`, `uv lock --check --offline` and `uv pip check` pass. Third-party extension types are isolated at the narrow engine bridge; mypy does not prove native implementation correctness. |
| CI | Same locked provisioning/offline checks configured in `.gitlab-ci.yml`; standard [GitLab secret detection](https://docs.gitlab.com/user/application_security/secret_detection/pipeline/) included. CI scripts exercised locally; server validation, runner execution and analyzer results are not claimed. |
| Safety | Application has no network client, broker configuration or order mode. Test socket access is denied; no real account, credentials, external data or services are used by tests. No real/simulated trade is submitted by the smoke run. |
| Preservation | Original Gemini report hashes and existing unrelated project memory remain protected; dependencies, environments, caches and build artifacts are ignored. |

NautilusTrader's run bookkeeping calls deprecated `Timestamp.utcnow()` under locked pandas 3.1.0, producing `Pandas4Warning` (12 warnings across the current suite). Tests/replay pass; the warning is left visible. Revisit upstream compatibility before a pandas major upgrade; no vendored patch or suppressed broad warning filter is introduced. A successful order-free smoke test verifies integration and causal event delivery only, not fills, fees, PnL, strategy correctness or live/backtest parity. Those gates remain later milestones.

All source links above were accessed 2026-10-29. M1 is complete locally; M2 has not started. Next proposed task is to specify the exact MES historical study period/contracts, required coverage, timestamp/rights evidence and IBKR-first feasibility checklist before any authorized acquisition.
