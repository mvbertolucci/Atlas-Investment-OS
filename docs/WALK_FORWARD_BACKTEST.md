# Deterministic Walk-Forward Backtest

## Purpose

PR-033 builds and tests the **replay mechanism** that consumes
`backtesting.point_in_time.PointInTimeDataset.as_of(decision_at)` (PR-032) and
recreates each Atlas decision using only evidence visible at that cutoff,
through the existing, unchanged, governed `scoring.investment.score_dataframe`.

**This is not, yet, a backtest of Atlas's real historical performance.**
PR-032 deliberately excluded historical-data acquisition (provider
credentials, a populated point-in-time dataset). No such dataset exists in
this repository. `backtesting/walk_forward.py` is proven with small, fully
synthetic, offline fixtures (`tests/test_walk_forward.py`) -- they establish
that the mechanism is correct (temporal exclusion, incomplete-decision
reporting, determinism), not that Atlas would have performed any particular
way historically. Acquiring a real, versioned, point-in-time-correct
historical dataset is a separate, later, and materially harder problem
(most free providers do not expose "value as known on date X" with revision
history) -- PR-034 (return/risk validation) still needs that dataset to mean
anything, and does not exist here either.

## Executable contract

`backtesting/walk_forward.py`:

- `HistoricalInputManifest` — versioned provenance, matching exactly the
  "Required provenance for PR-033" list in `docs/POINT_IN_TIME_DATA.md`:
  source name/version, benchmark and constituent-history source, decision
  calendar description and timezone, tracked fields, revision policy,
  delisting coverage and unresolved-event count, Atlas code revision and
  governed-config SHA-256 hashes. Every field is required and validated; an
  incomplete manifest fails to construct rather than being silently filled
  in with a placeholder.
- `compute_governed_config_hashes(paths)` — real SHA-256 of the governed
  config files actually used, so the manifest's provenance claim is
  independently verifiable, not just asserted.
- `reconstruct_snapshot_frame(snapshot)` — one row per active constituent,
  one column per field name actually observed in the snapshot, plus each
  field's observation date and split-alignment metadata. A member
  with zero observations still gets a row (so it can be reported, not
  silently dropped); no value is invented or borrowed from another date or
  symbol.
- `replay_decision_batch(snapshot, ...)` — runs the reconstructed frame
  through the real, unchanged `score_dataframe` (same governed `model.yaml` /
  `deal_breakers.json` as live scoring). A symbol is reported as an
  `IncompleteDecision` (never silently dropped or repaired) when:
  - it has a known, effective delisting with `return_treatment="unresolved"`;
  - it has zero observations available at that cutoff.
  Otherwise, Atlas's existing tolerant scoring (neutral factor default, lower
  `Model Confidence` for partially missing fields) already applies -- this
  engine does not duplicate or add a new confidence threshold.
  Before scoring, the replay derives single-period ratios, a two-10-K
  `f_score_annual`, and price-dependent valuation fields. A low derived
  F-Score flows through the unchanged governed Piotroski Deal Breaker.
- `run_walk_forward(dataset, decision_dates, manifest, ...)` — the engine:
  for each explicit decision date, gets the as-of snapshot and replays it.
  Dates are deduplicated and sorted; the same dataset + dates + governed
  config always produce byte-identical output (`tests/test_walk_forward.py`
  proves this, and separately proves that a value available only after one
  decision date does not leak into that decision even though the same
  dataset is later used for a date where it is visible).
- `monthly_decision_calendar(start, end, day_of_month=1)` — an optional,
  pure convenience for producing an explicit monthly calendar. The engine
  accepts any explicit iterable of dates; this is not required.
- `WalkForwardReport` / `write_walk_forward_report` — JSON output. Every
  report carries `"advisory_only": true` and an explicit
  `performance_disclaimer` field: this replays decisions, it does not
  compute or claim any return, risk or performance figure.

## Scope boundary

Explicitly out of scope for this increment, per the roadmap:

- a complete, broad populated point-in-time dataset;
- portfolio performance, return, drawdown or risk metrics (PR-034);
- a prospective shadow portfolio (PR-035);
- any change to governed scoring weights, thresholds or Deal Breakers;
- universe-eligibility or ranking replay (this engine replays the core
  decision engine only -- `score_dataframe` -- not `evaluate_universe` /
  `rank_companies` historically).

## Validation

`tests/test_walk_forward.py`: manifest validation (every required field,
rejecting an empty one), governed-config hashing (real files, deterministic),
frame reconstruction (no invented values, observation dates and split
alignment, members with no data still
represented), decision replay (complete case, no-data case, unresolved
delisting, resolved delisting, derived F-Score Deal Breaker), determinism,
the anti-look-ahead property end to end, date deduplication/sorting, the
monthly calendar helper, and report serialization. All offline, no network,
no live provider.
