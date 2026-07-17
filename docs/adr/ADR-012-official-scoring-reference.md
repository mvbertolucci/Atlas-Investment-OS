# ADR-012 — Official broad-market scoring reference

**Status:** Accepted  
**Date:** 2026-07-17

## Context

Atlas factor scores are percentile ranks. Previously every live invocation used
its own batch as the denominator, so watchlist membership could change a
company's score without any change in that company's evidence. The ticker mode
also had to download the whole watchlist merely to avoid an all-neutral
single-row score.

## Decision

The eligible U.S. broad-market snapshot is the official live-scoring reference.
`portfolio.model_portfolio --label market` now:

1. evaluates `config/universe_market.yaml` before scoring;
2. retains only eligible members for the reference distribution;
3. writes `output/dados/scoring_reference_market.json` with the universe id,
   snapshot date, eligible count, model version, reference version and sorted
   market/sector values for every governed feature;
4. scores the collected frame against that immutable distribution.

`run_all.py` and `--ticker` load the artifact and never add watchlist or
portfolio rows to its denominator. Accounting, balance-sheet and valuation
features marked `percentile_scope: sector` in `config/features.yaml` use their
sector distribution when it has at least five observations, otherwise the
market distribution. Timing and Piotroski remain market-relative.

Every scored row carries `reference_universe`, `reference_date`,
`reference_count` and `reference_version`. The history database persists these
fields. If the reference is absent, corrupt, belongs to another universe or was
built for another model version, live scoring falls back explicitly to the old
current-batch behavior and records `reference_universe=CURRENT_BATCH`; it never
silently labels that result as official.

Historical walk-forward scoring does not load the current artifact. A future
historical reference must be built independently at each cutoff to preserve the
point-in-time boundary.

## Consequences

- Live watchlist, portfolio and ticker scores are comparable while the official
  reference version remains unchanged.
- Refreshing the market collection/reference is a governed score-baseline
  event, even when weights do not change.
- Sector-relative features reduce structural cross-sector distortion but make
  the recorded sector classification financially material.
- The compact artifact is generated locally and remains gitignored with other
  runtime data.

## Rollback

Disable use of the artifact by removing or renaming
`scoring_reference_path` in local settings, or revert this ADR and the optional
`scoring_reference` arguments. Existing call sites without a reference retain
the legacy current-batch calculation.
