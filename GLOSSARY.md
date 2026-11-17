# Drift

Vocabulary for the platform's research and trading domain.

## Language

**Agent**: A versioned decision component that consumes information available at a specified time and emits proposals. It belongs to the rule-based, ML or LLM family; family does not determine its instrument or deployment mode.
_Avoid_: Autonomous broker, LLM as a synonym for every agent

**Proposal**: An agent's directional suggestion or research advisory, with provenance and a validity period. It conveys no permission to trade.
_Avoid_: Order, approved trade

**Order intent**: A specific execution request authorized by shared portfolio and risk policy. An intent is distinct from a broker's acknowledged order and actual fills.

**Strategy**: A decision policy under investigation or evaluation, potentially represented by one or several agents.

**Experiment**: A preregistered, reproducible test of a strategy or model hypothesis, including unsuccessful trials.

**Virtual portfolio**: A persistent simulated account binding one strategy to its own capital, configuration history and chain of segments. Unrelated to any broker account.
_Avoid_: Paper account

**Segment**: One committed backtest run in a virtual portfolio's chain, trading a window that starts exactly where the previous one stopped.

**Replay**: Feeding a fresh agent the portfolio's candle history, with no quotes and no decisions, to rebuild its state before a segment trades.

**Run**: One backtest of one strategy over one window, identified by a hash of its inputs. A **batch** is one attempt at a set of runs, and is logged even when they fail.

**Availability time**: The earliest time an observation could have been used by the decision process, accounting for completion, publication and delivery. It can differ from the event timestamp and acquisition date.

**Instrument**: An identified tradable product with a defined share class or contract, currency and trading specifications. Provider tickers and broker identifiers can refer to the same instrument without being interchangeable identifiers.

**Contract**: A particular derivative instrument with its own specifications and, where applicable, expiry. A continuous futures series is a research representation, not an executable contract.

**Data provider**: A source of market observations under a specific feed and use agreement. It can differ from the broker executing trades.

**Feed**: A defined stream or historical collection of market observations with particular venue coverage, construction and timeliness. Different feeds for the same instrument need not contain identical bars.

**Corporate action**: An issuer event affecting a security's shares or distributions. A split changes the share/price basis; adjusted research values and raw executable prices represent different views.

**Admission**: An evidence-based decision that a specified dataset, instrument or execution route is suitable for a declared use. It does not by itself authorize an account connection or trading.

**Paper trading**: Broker-simulated execution on an explicitly selected paper account. Its fills do not establish live execution quality or profitability.

**Opening range**: The high and low of the first 5, 15 or 30 minutes of the cash session from 09:30 New York. An opening range breakout trades a completed close beyond it.

**Session VWAP**: The volume-weighted average of typical price, `(high + low + close) / 3`, from the session open through the latest available candle. VWAP and Bollinger mean reversion fade a fresh move of the close beyond a multiple of the matching dispersion.
_Avoid_: Using a full-session VWAP for a decision made earlier in the session

**Statistical rule agent**: A rule-based agent that turns completed price-series readings (breakout, mean reversion, reversal, trend, momentum) into proposals. Relative-strength agents need benchmark data and are future work.

