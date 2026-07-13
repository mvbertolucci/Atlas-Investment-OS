# Historical Model-Portfolio Targets

## Purpose

`backtesting/historical_portfolio.py` connects the PR-033 point-in-time replay
to the PR-034 portfolio-validation contract. At each explicit cutoff it uses
the same snapshot reconstruction, factor derivation, governed scoring,
universe eligibility, ranking and model-portfolio policies as the current
research pipeline.

This produces historical **targets**, not assumed trades and not performance.
No provider is called and no current observation is projected backward.

## Single scoring route

`backtesting.walk_forward.score_snapshot_batch` owns snapshot reconstruction,
incomplete-decision detection, point-in-time factor derivation and governed
scoring. Both decision replay and historical portfolio construction consume
that function. A later change therefore cannot silently give the portfolio a
different scoring route from the replay.

Each `HistoricalTargetPortfolio` contains:

- the timezone-aware decision cutoff;
- target weights and explicit sectors when construction succeeds;
- active-member, eligible and candidate coverage counts;
- every incomplete decision and its machine-readable reasons;
- SHA-256 hashes of the model, Deal Breakers, universe, ranking and
  model-portfolio configurations used;
- an explicit construction error and no positions when constraints cannot be
  satisfied.

Insufficient candidates never produce a smaller accidental portfolio.
`build_historical_target_portfolios` sorts and deduplicates explicit cutoffs
and applies the same contract independently to every snapshot.

## Decision time is not execution time

A target cannot enter return validation until an explicit execution convention
converts it to a rebalance. `backtesting/historical_execution.py` now governs
that boundary as the first attributed session opening strictly after the
decision, requiring a price for every position. The lower-level
`target.to_rebalance(effective_on)` still requires an explicit date and rejects
dates before the decision.

Weekends and holidays come from supplied session evidence, never a weekday
guess. See `docs/HISTORICAL_EXECUTION.md`. Until a real versioned calendar,
opening-price evidence and total returns exist, these targets must not be
described as historical performance.

## Remaining boundary

- acquire and version the real exchange calendar and opening-price evidence;
- acquire complete, dividend-inclusive returns for every held symbol and the
  benchmark, including terminal-event treatment;
- map explicit effective dates to validation periods;
- add factor contribution and run broad real validation.
