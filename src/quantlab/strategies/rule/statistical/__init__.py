"""Statistical rule strategies: one deterministic model per module, sharing `session` state.

`itsm` (EXP-001 momentum), `orb` (opening range breakout), `vwap_reversion` and
`bollinger_reversion` (mean reversion, sharing the `fade` core), `reversal` (short-term
reversal) and `trend` (moving-average trend following). Candlestick patterns are the sibling
family in `rule.candlestick`.
"""
