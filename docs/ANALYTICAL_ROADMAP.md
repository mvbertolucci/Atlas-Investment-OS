# Analytical Roadmap — Market to Model Portfolio

## Objective

Evolve Atlas from analysis of a manually selected watchlist into a reproducible
method that maps an explicit market universe, ranks eligible companies, builds
an advisory model portfolio and validates it without look-ahead bias.

The analytical track has priority over Scheduling, Notifications and the AI
assistant. It remains decision support: no trade execution and no performance
promise.

## Sequence

1. **PR-027 — Market Universe and Analytical Method Contract.** Define the
   initial universe, benchmark, rebalance frequency, minimum liquidity and data
   requirements, with standardized exclusion reasons and coverage reporting.
2. **PR-028 — Market Mapper integration (complete).** Enrich provider output with asset
   type and liquidity fields, evaluate the configured universe in the main
   pipeline and publish the universe report.
3. **PR-029 — Robust analytical ranking (complete).** Separate relative market/sector
   rank from absolute economic safeguards; do not change governed weights
   without evidence.
4. **PR-030A — Reproducible universe expansion (complete).** Maintain a dated,
   attributed snapshot of the broad research population, distinct from the
   personal watchlist, with deterministic batch boundaries.
5. **PR-030B — Incremental broad-universe collection (complete).** Collect, retry and
   checkpoint bounded batches without losing completed market observations.
6. **PR-031 — Advisory model-portfolio builder (complete).** Select eligible candidates
   and assign transparent weights under position, sector, cash and turnover
   constraints.
7. **PR-032 — Point-in-time data contract.** Define observation, availability,
   constituent and delisting rules required to avoid future-data and
   survivorship bias.
8. **PR-033 — Walk-forward backtest.** Recreate each decision using only data
   available at that date and compare against explicit benchmarks.
9. **PR-034 — Portfolio validation.** Report return, volatility, drawdown,
   turnover, estimated costs, concentration and factor contribution.
10. **PR-035 — Prospective shadow portfolio.** Freeze real-time model-portfolio
   recommendations and evaluate them forward without capital or broker access.
11. **PR-036 — Controlled calibration.** Consider weight or threshold changes
   only from versioned, out-of-sample evidence.

## Initial universe policy

The canonical `config/universe.yaml` starts deliberately narrow:

- U.S. listed equities represented by `quote_type: EQUITY`;
- USD and United States domicile;
- minimum USD 1 billion market capitalization;
- minimum USD 5 observed price;
- minimum 100,000 observed daily volume;
- monthly rebalance frequency;
- S&P 500 analytical benchmark.

These are research eligibility rules, not recommendations. They are explicit
and version-controlled so later changes can be measured rather than silently
changing the tested population.

## PR-027 boundary

PR-027 added only a domain contract and pure evaluation over an existing
DataFrame. PR-028 adds provider and pipeline exposure, but remains diagnostic:
ineligible assets are reported, not removed from scoring. Market expansion and
candidate discovery remain separate from the configured watchlist.

PR-029 orders eligible companies by existing Atlas scores and applies the
existing governed Deal Breakers plus a data-confidence floor. It creates no new
composite score. See `docs/RANKING_METHOD.md`.

PR-030A expands the source population to a dated 503-security snapshot while
keeping the personal watchlist unchanged. It does not yet trigger hundreds of
provider requests; see `docs/UNIVERSE_SOURCES.md`.

PR-030B adds a manually invoked, one-batch-at-a-time collector with atomic
checkpoints, retries and safe resume. It does not alter `run_all.py`, scores or
the watchlist; see `docs/UNIVERSE_COLLECTION.md`.

PR-031 applies the existing governed score, universe and ranking contracts to a
complete checkpoint, then selects 20 equal-weight positions under explicit
position and sector caps. See `docs/MODEL_PORTFOLIO.md`.

## Validation principles

- Every exclusion has a machine-readable reason.
- Missing required data excludes an asset instead of silently imputing
  eligibility.
- Duplicate symbols are explicit failures.
- Backtests must distinguish in-sample, validation and untouched test periods.
- Historical fundamentals require an availability date; current fundamentals
  must never be projected backward.
- Historical universe membership must include removals and delistings.
- Returns must state dividend, currency, fee, tax and transaction-cost
  treatment.
- A shadow portfolio is forward evidence, not a promise of performance.
