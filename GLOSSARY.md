# Quant Trading Lab

Vocabulary for the platform's research and trading domain.

## Language

**Agent**: A versioned decision component that consumes information available at a specified time and emits proposals. It belongs to the rule-based, ML or LLM family; family does not determine its instrument or deployment mode.
_Avoid_: Autonomous broker, LLM as a synonym for every agent

**Proposal**: An agent's directional suggestion or research advisory, with provenance and a validity period. It conveys no permission to trade.
_Avoid_: Order, approved trade

**Order intent**: A specific execution request authorized by shared portfolio and risk policy. An intent is distinct from a broker's acknowledged order and actual fills.

**Strategy**: A decision policy under investigation or evaluation, potentially represented by one or several agents.

**Experiment**: A preregistered, reproducible test of a strategy or model hypothesis, including unsuccessful trials.

**Availability time**: The earliest time an observation could have been used by the decision process, accounting for completion, publication and delivery. It can differ from the event timestamp and acquisition date.

**Contract**: A venue-qualified tradable instrument with its own expiry and specifications. A continuous futures series is a research representation, not a contract that can receive orders.

**Paper trading**: Broker-simulated execution on an explicitly selected paper account. Its fills do not establish live execution quality or profitability.
