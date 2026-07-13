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

## PR-019.4 hit rate and calibration

Directional hit rate uses the following explicit expectations:

- `STRONG_BUY`, `BUY` and `ACCUMULATE`: positive return;
- `AVOID`: negative return;
- `HOLD` and `WATCH`: excluded from directional hit rate.

The strict success threshold defaults to `0.0%` and can be increased through
`outcome_hit_threshold_pct`. A return equal to the threshold is not a hit.

Opportunity and Conviction calibration is calculated independently by horizon
and score bucket. Each bucket reports observation count, average score, average
return and positive-return rate. The default bucket width is 20 points and is
configured through `outcome_calibration_bucket_size`.

Calibration is descriptive. It does not change Atlas weights, thresholds or
decisions.

### Known limitation — relative scores across runs

Score buckets pool observations across all decision dates. Atlas factor and
investment scores are cross-sectional percentile ranks within each run's
watchlist batch (see `docs/SCORING_MODEL.md`), so a given bucket (for example
`[80, 100)`) does not mean the same absolute quality across runs when the
watchlist composition changes. Calibration is therefore only strictly
comparable while the watchlist is stable; otherwise treat cross-run calibration
as indicative rather than absolute. Hit rate and decision/Deal-Breaker
attribution are less exposed because they key on the categorical decision, not
the score level.

#### Drift safeguard

`calculate_watchlist_drift` turns that assumption into a signal. For each
transition between consecutive decision dates it reports the Jaccard overlap of
the analyzed symbol sets and how many symbols entered/left, with `stable` when
nothing changed. The result is exposed as the additive `watchlist_drift` field
in `outcome_report.json` (existing fields are unchanged), and
`build_outcome_analytics_report` logs a warning when any transition is
unstable. It is diagnostic only — it changes no score, weight or decision. With
fewer than two decision dates it is empty.

## PR-019.5 attribution

Decision snapshots now retain Business, Valuation, Financial and Timing scores,
plus the names of triggered Deal Breakers. Existing SQLite databases receive
these columns through an additive migration.

Attribution remains separated by horizon and reports sample count, average
return and positive-return rate for:

- each factor-score band;
- each final decision code;
- each named Deal Breaker;
- the explicit `NO_DEAL_BREAKER` baseline.

Attribution is descriptive and does not establish causality. Multiple Deal
Breakers on one decision contribute one observation to each applicable group.

## PR-019.6 reporting

Each enabled main-pipeline run publishes `output/outcome_report.json` as the
machine-readable analytical contract. The Excel workbook conditionally adds
`Outcome Summary`, `Outcome Calibration` and `Outcome Attribution` worksheets.
Morning Brief adds the directional hit rate, mature results by horizon and the
calibration bands with the largest samples.

When no directional result has matured, the report explicitly states that the
sample is insufficient. Reporting is descriptive and does not modify weights,
thresholds, Deal Breakers or final decisions. Live provider access remains
outside deterministic tests.
