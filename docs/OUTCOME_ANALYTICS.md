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

## PR-019.3 horizon returns

Each main-pipeline run evaluates stored decisions whose configured horizon has
matured. The first valid Atlas price observed on or after the due timestamp is
stored as an immutable `OutcomeResult`.

Each result records decision date, symbol, horizon, due date, evaluation date,
evaluation lag, both prices and the simple percentage return. The
`outcome_results` table is keyed by decision, symbol and horizon, so later runs
do not overwrite the first observation. Missing prices can be evaluated later.

Returns do not include dividends, fees, taxes or currency conversion.

## Deliberate boundaries

Outcome Analytics does not yet calculate hit rate, score calibration or factor
attribution. These derived metrics consume persisted results in later stages.

## Next increment

PR-019.4 should calculate hit rate and Opportunity/Conviction calibration from
persisted results. Live provider access must remain outside deterministic tests.
