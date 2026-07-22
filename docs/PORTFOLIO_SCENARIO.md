# Portfolio Pre-trade Scenario

`output/dados/portfolio_scenario.json` is a versioned, advisory-only simulation
of executing the official `SELL` and `TRIM` trade values already present in the
portfolio rebalance report.

The scenario never creates a trade, chooses a replacement or changes a target.
It ignores `HOLD`, `REVISAR` and `ACOMPANHAR`. It reports released cash,
post-trade cash and cash weight, turnover, optional transaction cost, remaining
symbol/sector weights and post-trade concentration. Total portfolio value is
the fixed denominator; transaction costs, when configured by the caller, are
deducted from cash.

The current scenario is embedded in Dashboard contract v1.3 and summarized in
`decision_cockpit.html`. Replacement-buy and user-adjustable scenarios remain
separate future increments.
