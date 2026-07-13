# Historical Execution Convention

## Purpose

`backtesting/historical_execution.py` supplies the explicit boundary between a
point-in-time model-portfolio target and a validation rebalance. It performs no
provider request and does not simulate orders, fills, shares or market impact.
It consumes attributed trading sessions and opening-price observations.
`backtesting/execution_evidence.py` can now produce those contracts from
already-acquired Yahoo-shaped bars in a versioned JSON artifact; see
`docs/EXECUTION_EVIDENCE.md`.

## Governed convention

`config/historical_execution.yaml` pins the initial convention:

- execute at the first session opening strictly after `decision_at`;
- allow at most seven calendar days to reach that opening;
- require USD opening prices for every target position;
- reject the entire execution if any price is absent or mismatched.

"Next session" means the first supplied exchange session whose timezone-aware
opening timestamp is later than the cutoff. If a decision is finalized before
the same day's opening, that opening may be selected. If the cutoff is at or
after the opening, the next supplied session is required. Weekends and holidays
are represented by the attributed session calendar, not guessed from weekdays.

This next-session-open assumption avoids using the same closing price that fed
the decision. It is a research convention, not a claim that Atlas could obtain
every official opening print in live trading.

## Evidence contract

- `TradingSession` provides an explicit session date, UTC-normalizable opening
  timestamp, venue and source.
- `ExecutionPriceObservation` provides symbol, exact opening timestamp,
  positive price, currency and source.
- Duplicate sessions or symbol/timestamp prices are invalid.
- `HistoricalExecutionResult` embeds the governed policy, selected session,
  all accepted prices and any machine-readable failure reasons.

An unconstructed target, absent future session, excessive wait, missing price
or currency mismatch produces no `PortfolioRebalance`. Available prices remain
visible for diagnosis, but Atlas never creates a partial rebalance. Successful
execution preserves the target weights/sectors and uses the explicit exchange
session date as `effective_on`.

## Remaining boundary

The repository now has a versioned artifact schema and pure Yahoo-bar adapter,
but no broad real artifact has been collected. Real reference/position bars
must still be acquired and kept as attributed runtime data before targets can
be executed at scale. Complete
dividend-inclusive holding-period returns and terminal-event evidence are also
still required before the PR-034 metric runner can produce real results.
