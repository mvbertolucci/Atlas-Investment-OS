# Outcome Analytics

## Objective

Outcome Analytics measures what happened after an Atlas decision. It evaluates
decision quality; it does not promise future performance and does not execute
trades.

## PR-019.1 foundation

`outcomes.models.OutcomeSnapshot` is the immutable decision-time contract. It
records:

- decision timestamp and symbol;
- observed decision price;
- Atlas decision and presentation rating;
- Investment, Opportunity, Conviction and Decision Confidence scores;
- risk penalty and Deal Breaker presence.

Snapshots are persisted in the existing local history database through
`HistoryDatabase`. The additive `outcome_snapshots` table is keyed by decision
timestamp and symbol, so repeated writes replace the same logical decision
without duplicating it. Existing `snapshots` history remains unchanged.

## Deliberate boundaries

PR-019.1 does not:

- capture snapshots automatically from `run_all.py`;
- fetch future prices;
- choose or calculate performance horizons;
- calculate returns, hit rate or calibration;
- attribute performance to factors or rules.

These boundaries keep the decision event separate from later evaluation.

## Next increment

PR-019.2 should define configurable evaluation horizons and connect successful
company-analysis runs to `OutcomeSnapshot` creation. Live provider access must
remain outside deterministic tests.
