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

## PR-019.2 automatic capture

Successful main-pipeline runs now create outcome snapshots immediately after the
normal history snapshot. Runtime settings control this behavior:

```json
{
  "outcome_analytics_enabled": true,
  "outcome_horizons_days": [30, 90, 180, 365]
}
```

Horizons must be unique positive integer days. They are normalized and sorted.
Assets without a valid positive decision price are reported as skipped without
preventing valid assets from being stored.

## Deliberate boundaries

PR-019.1 does not:

- fetch future prices;
- calculate performance at the configured horizons;
- calculate returns, hit rate or calibration;
- attribute performance to factors or rules.

These boundaries keep the decision event separate from later evaluation.

## Next increment

PR-019.3 should evaluate future prices and persist returns for each configured
horizon. Live provider access must remain outside deterministic tests.
