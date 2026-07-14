# Changelog

## Broad-market advisory ranking run

### Completed

- Re-ran the broad-market model-portfolio pipeline offline from the completed
  7,093-symbol snapshot and checkpoint, without provider calls.
- 6,959 observations produced 2,429 policy-eligible companies and 999
  safeguarded candidates; 134 exhausted provider failures remain attributed
  under `source.excluded_failures` instead of being silently dropped.
- The constrained advisory result contains 20 equal-weight positions. Total
  weight is 100%, maximum position weight is 5% and Healthcare/Technology
  each stop exactly at the governed 20% sector cap.
- `CRMD` (candidate 14) and `CRUS` (candidate 21) were the two higher-ranked
  names skipped by those sector constraints; the complete ordered shortlist
  remains in the ignored `output/research_candidates_market.csv` artifact.

### Preserved

- Runtime market artifacts remain ignored and are not performance evidence,
  trade orders or a change to scoring, Deal Breakers or portfolio policy.
- The ADR policy pass and broad point-in-time historical validation remain
  separate open work.

## Add universe provenance to the pipeline

### Added

- `origin` column on the analyzed DataFrame: `run_all.merge_watchlist_with_portfolio`
  now tags every row `portfolio` or `watchlist` (hierarchy `portfolio >
  watchlist`, ready for a future `> universe` tier once the broad-market
  screener merges into the same universe), and `collect_market_data`
  reattaches it by symbol after `providers.yahoo.fetch_watchlist` (which
  rebuilds each row from scratch and would otherwise drop it).
- `Holding.origin` (`portfolio/models.py`): filled by
  `enrich_portfolio_from_analysis` from the analyzed row's `origin` --
  the verified source of truth, never assumed just because a symbol
  appears in `Portfolio.holdings`.
- `ranking.RankedCompany.already_held` (`ranking/models.py`,
  `ranking/pipeline.py`): `True` when a row's `origin == "portfolio"`,
  `False` (never invented) when the frame carries no `origin` column at
  all (point-in-time replay, standalone research collection).

### Fixed

- `portfolio.rebalance.build_sell_only_plan` had no defense against acting
  on a holding whose provenance wasn't actually the real portfolio -- it
  trusted `Portfolio.holdings` unconditionally. A regression test proved
  this by constructing a `Portfolio` from a watchlist-only symbol and
  showing the engine happily emitted an action for it. Now checks
  `Holding.origin` and skips (never SELL, never HOLD) any holding whose
  verified origin is not `portfolio`, with an explicit warning listing the
  skipped symbols.

### Validation

- 604 automated tests passed.
- 88.61% production coverage overall.

## Decouple the research watchlist from the real portfolio

### Fixed

- `config/watchlist.csv` (manually curated research symbols) had been
  overwritten with the real portfolio's 24 symbols earlier the same day, to
  give `portfolio.rebalance`'s sell-only engine a `CompanyReport` for every
  holding. That conflated two conceptually distinct sources -- assets the
  user chose to track versus real holdings pulled from the user's actual
  investment file. Restored `config/watchlist.csv` to its intended six
  research symbols (Adobe, FMC, Microsoft, Lockheed Martin, AMD, Akamai).

### Added

- `run_all.merge_watchlist_with_portfolio(watchlist, settings)`: merges
  `config/portfolio.csv`'s symbols into the analysis universe **only in
  memory**, for the duration of one run -- never written back to either
  CSV. Every real holding still gets a scored `CompanyReport` (required for
  sell-only rebalance), and the manually curated watchlist stays exactly
  what the user put there. Symbols already on the watchlist are not
  duplicated; a missing or unreadable `portfolio.csv` degrades gracefully
  to watchlist-only analysis, matching pre-portfolio behavior.

### Validation

- 598 automated tests passed.
- 88.62% production coverage overall.

## PR-034 — Weighted-average factor exposure

### Added

- `PortfolioRebalance.factor_exposures` in `backtesting/portfolio_validation.py`:
  an optional per-symbol map of `{business, valuation, financial, timing}`
  scores (0-100), validated to use the same factor set across every symbol
  that has one.
- `ValidationPeriod.factor_exposures`: the portfolio's target-weighted
  average exposure per factor for each complete period, `null` unless every
  held symbol has a value for the exact same factor set.
- `backtesting/historical_portfolio.py` now reads these factor scores
  straight from the governed scoring pass (`factors/engine.py`'s
  `Business Factor`/`Valuation Factor`/`Financial Factor`/`Timing Factor`
  columns) at each historical cutoff -- not recomputed, not a new data
  source, just no longer discarded after `score_snapshot_batch`.
  `HistoricalTargetPortfolio.to_rebalance()` carries them straight into the
  resulting `PortfolioRebalance`.

### Preserved

- This is a composition/tilt summary, not a return decomposition -- it does
  not attribute period *return* to each factor the way
  `sector_contributions` attributes return to sectors. A regression-based
  factor-return decomposition remains explicitly out of scope: it needs a
  statistical methodology to validate and document, not just a data join.
- `null` under partial or absent coverage, never an invented value.

### Validation

- 593 automated tests passed.
- 88.63% production coverage overall.

## PR-034 — Per-sector return contribution

### Added

- `ValidationPeriod.sector_contributions` in `backtesting/portfolio_validation.py`:
  `target_weight × asset_return`, summed per sector, for each complete
  validation period, reusing the existing `PortfolioRebalance.sectors`
  mapping already required for `sector_hhi` -- no new input contract needed.

### Preserved

- `null` under the exact same absent/partial-sector-coverage rule as
  `sector_hhi`/`maximum_sector_weight`, never an invented classification.
- Values always sum to exactly `gross_return`, a useful invariant pinned by
  a regression test.
- Factor contribution (scoring-factor exposures at each cutoff) remains
  explicitly out of scope: it needs those exposures joined into the input
  contract without look-ahead, which the existing contract does not carry.

### Validation

- 587 automated tests passed.
- 88.58% production coverage overall.

## PR-034 — Versioned dividend-inclusive total-return evidence

### Added

- `backtesting/total_return_evidence.py`: a pure, offline adapter converting
  already-acquired Yahoo-shaped daily bars (`Close`, `Dividends`) into the
  `AssetPeriodReturn` rows `backtesting/portfolio_validation.py` already
  consumes, for an explicit, caller-supplied sequence of period boundaries.
  Works identically for a portfolio holding or the benchmark symbol.
- Dividend-inclusive total return by compounding `(Close[t] + Dividend[t]) /
  Close[t-1]` day over day across each period -- no explicit split-ratio
  handling needed, since Yahoo's own retroactive split-continuity convention
  applies consistently to both raw columns and cancels out in the ratio.
- `DelistingRecord` (PR-032 vocabulary) terminal-event handling, scoped to
  only the one period containing `last_trade_on`: `zero` forces exactly
  -100%; `cash` combines the compounded multiplier up to the last traded
  close with `cash_proceeds`; `successor` and `unresolved` are both reported
  `unresolved` (`total_return=None`).
- `TotalReturnEvidence`: a versioned, retrieval-timestamped artifact
  (schema_version 1) wrapping a batch of these rows, mirroring
  `backtesting/execution_evidence.py`'s `HistoricalExecutionEvidence`
  pattern, so total returns can be computed once and reused across
  validation runs.

### Preserved

- A period whose start date has no observed close is omitted, never
  invented -- `validate_portfolio` already reports
  `MISSING_RETURN`/`MISSING_BENCHMARK_RETURN` for anything absent.
- A `successor` delisting is never assigned a fabricated return: this
  single-symbol adapter has no evidence of a successor security's own value.
- No provider call; the adapter is pure and offline, exactly like
  `execution_evidence.py`.

### Validation

- 585 automated tests passed.
- 88.57% production coverage overall.

## PR-034 — Deterministic portfolio-validation core

### Added

- Source-attributed contracts for dated target weights and total-return
  observations, including currency, dividend and terminal-event treatment.
- A governed monthly validation policy with SPY total return, USD, dividends
  included and an explicit 10 bps one-way transaction-cost estimate.
- Portfolio/benchmark return, annualized volatility, maximum drawdown,
  drift-aware turnover, estimated costs and position-concentration metrics.
- Machine-readable incomplete periods. Missing returns, assumption mismatches
  or unresolved delistings suppress aggregate metrics instead of silently
  biasing the result.
- A schema-versioned, offline JSON runner and CLI with mandatory dataset,
  portfolio, return, benchmark, terminal-event and code-revision provenance.
- Sector HHI and maximum sector weight when every position has an explicit
  sector; incomplete sector coverage remains `null`, never imputed.
- A loadable synthetic input example that documents the schema without
  presenting fabricated returns as research evidence.
- Point-in-time historical portfolio targets built through the exact PR-033
  scoring route and the governed universe, ranking and model-portfolio paths.
- Visible incomplete-decision coverage, governed-config hashes and explicit
  construction errors instead of smaller accidental portfolios.
- An explicit target-to-rebalance boundary requiring the caller to provide an
  execution date that cannot precede the decision cutoff.
- A governed next-session-open execution policy with explicit exchange-session
  and opening-price evidence, a seven-calendar-day maximum wait and no partial
  execution when any position price is missing.
- Audit output retaining the policy, selected session, accepted prices and
  machine-readable failure reasons; no provider or order simulation added.
- A schema-versioned execution-evidence artifact plus pure adapter from
  Yahoo-shaped bars to observed SPY-proxy sessions and opening prices.
- `America/New_York` DST-aware 09:30 timestamps, reference-session filtering
  and split-restored as-traded `Open` units, with manifest/temporal validation.

### Preserved

- No provider call, broad collection, score, Deal Breaker, governed model
  weight, historical portfolio construction or real performance claim.
- Factor contribution and a broad real validation remain open PR-034 work.

### Validation

- 41 deterministic PR-034 tests cover historical targets, anti-look-ahead,
  execution evidence, next-session execution, calculations, costs, drift-aware
  turnover, terminal events, missing evidence, assumptions and report
  serialization.
- 570 automated tests passed.
- 88.50% production coverage overall; historical-target, execution-evidence,
  execution and validation modules have 87%, 87%, 90% and 90% direct coverage,
  respectively.

## Collector advancement after permanent provider failures

### Fixed

- Default `universe.collector` batch selection now treats a provider failure
  as resolved for advancement after its cumulative attempts consume the
  configured initial-attempt-plus-retries budget. A delisted or otherwise
  permanently unavailable ticker can no longer pin every later invocation to
  the same batch.
- Exhausted failures remain recorded in the checkpoint, are reported when all
  batches have been resolved, and can still be retried with an explicit
  `--batch-number`. The same behavior applies to the S&P 500 and broad-market
  screeners.

### Validation

- Deterministic regression coverage exercises the default no-`--batch-number`
  path, retryable-versus-exhausted boundaries, retained failure evidence and
  final reporting.
- 529 automated tests passed.
- 88.40% production coverage overall.

## Extended point-in-time valuation coverage

### Added

- Two new SEC EDGAR tags (`backtesting/sec_edgar.py`):
  `capital_expenditures` (`us-gaap:PaymentsToAcquirePropertyPlantAndEquipment`)
  and `dividends_paid` (`us-gaap:PaymentsOfDividends`/
  `PaymentsOfDividendsCommonStock`).
- `backtesting/point_in_time_valuation.py` now also derives
  `enterprise_value` (`market_cap + long_term_debt - cash_and_equivalents`),
  `ev_ebit`, `free_cash_flow` (`operating_cash_flow - capital_expenditures`),
  `fcf_yield` and `shareholder_yield`, each mirroring the exact formula
  `analytics/mapper.py` already uses for live Yahoo data.

### Preserved

- Assign-if-absent, missing-not-invented: a ratio is absent when its raw
  components are absent, never approximated.
- One documented adaptation: `shareholder_yield`'s dividend leg uses
  aggregate `dividends_paid / market_cap` (the live mapper instead uses
  per-share `dividend_rate / price`, since no clean per-share dividend tag
  is collected); missing dividend or buyback data reads as "no
  distribution of that kind" (mirroring the live mapper's `fillna(0.0)`
  per leg), not "unknown".
- `forward_pe`, `peg` and `ev_ebitda` remain explicitly out of scope: the
  first two need analyst estimates with no free point-in-time source
  integrated, and the live pipeline has no `ev_ebitda` formula of its own
  to mirror (it passes through Yahoo's `enterpriseToEbitda` directly) --
  inventing one without a live reference would be a new, undocumented
  approximation.

### Validation

- 525 automated tests passed.
- 87.83% production coverage overall.

## Point-in-time timing-factor derivation

### Added

- `backtesting/point_in_time_timing.py`: derives `rsi_14`,
  `momentum_3m/6m/12m` and `distance_52w_high` from the complete price
  history visible in each `AsOfSnapshot`, mirroring
  `analytics/indicators.py`'s exact formulas and trading-day windows.
- A continuous, split-adjusted close series per symbol: each earlier
  as-traded price is divided only by split ratios effective after that
  price and on or before the cutoff's latest visible price date, using
  only `snapshot.splits`.
- Wired into `walk_forward.replay_decision_batch`, alongside the existing
  ratio, F-Score and valuation derivation steps.

### Preserved

- A symbol without enough visible history for a given window leaves only
  that indicator missing (NaN), never inferred or borrowed.
- A split not yet known at the cutoff, or a price beyond the cutoff, never
  adjusts or enters an earlier replay's series.
- Preexisting timing values already supplied by the input frame are never
  overwritten. `target_upside` remains unbuilt.

### Validation

- 515 automated tests passed.
- 87.80% production coverage overall.

## Two-fiscal-year point-in-time F-Score

### Added

- Complete available observation history retained in each as-of snapshot.
- Deterministic 10-K grouping by accession, fiscal period and amendment.
- Piotroski F-Score derived only from two complete, consecutive annual periods.
- Split-normalized share comparison for the no-dilution signal.
- Direct integration with the existing governed `Piotroski baixo` Deal Breaker.

### Preserved

- Quarterly filings, incomplete years and non-consecutive periods never produce
  a partial score.
- Future filings and amendments do not leak into earlier decision cutoffs.
- Existing F-Score values, governed thresholds and scoring weights are not
  overwritten or changed.

### Validation

- 506 automated tests passed.
- 87.67% production coverage overall.

## Point-in-time stock-split normalization

### Added

- Explicit forward/reverse `StockSplitRecord` events in the point-in-time
  dataset and as-of snapshot.
- Restoration of Yahoo's split-normalized closes to as-traded historical
  prices.
- Per-field observation dates and cumulative share-count adjustment between
  the SEC observation date and paired price date.
- Auditable `shares_outstanding_split_adjusted` input for `market_cap`, `pe`,
  `pb` and `altman_z`.

### Preserved

- Split events never enter an as-of snapshot before they are effective and
  available.
- No governed score weight, threshold, Deal Breaker or live pipeline behavior
  changed.
- No performance or risk result was introduced.

### Validation

- 497 automated tests passed.
- 87.51% production coverage overall.
- Market capitalization remains continuous in a synthetic 4-for-1 split
  regression; forward and reverse event extraction are covered offline.
- A live Apple 2020 spot check restored Yahoo's normalized 124.8075 close to
  approximately 499.23 before the 4-for-1 split and left the split-date close
  unchanged.

## PR-032 — Point-in-time historical-data contract

### Added

- Immutable, source-versioned historical observation contract with separate
  observation and public-availability dates.
- UTC-normalized as-of snapshots that exclude future information and preserve
  source revisions.
- Non-overlapping, half-open historical constituent intervals for additions,
  removals and re-entries.
- Explicit cash, zero, successor or unresolved treatment for delistings.
- Canonical data and provenance rules in `docs/POINT_IN_TIME_DATA.md`.

### Preserved

- No historical provider, backtest, performance metric or calibration added.
- No score, governed configuration, ranking, decision or portfolio behavior
  changed.
- The current broad-universe snapshot remains current research evidence only.

### Validation

- 370 automated tests passed.
- 87.43% production coverage overall.

## PR-031 — Constrained advisory model portfolio

### Added

- Broad-universe analysis over the completed local collection checkpoint.
- Versioned equal-weight portfolio policy: 20 positions, 5% position cap, 20%
  sector cap, no structural cash and 100% maximum initial turnover.
- Advisory portfolio contract with ranks, existing scores, reference prices,
  target and sector weights, source dates and diversification warnings.
- Local broad universe, ranking and model-portfolio JSON outputs.

### Preserved

- No new alpha score and no change to governed score weights, Deal Breakers or
  ranking safeguards.
- `run_all.py`, the personal watchlist and the real portfolio remain unchanged.
- Output is advisory only and is not historical validation or a trade order.

### Validation

- 355 automated tests passed.
- 87.33% production coverage overall.
- Operational broad run: 503 observations, 475 universe-eligible companies,
  253 safeguarded candidates and 20 constrained model positions.

## PR-030B — Checkpointed broad-universe collection

### Added

- One-batch-at-a-time Yahoo collection over the versioned research universe.
- Atomic local checkpoint after every attempted symbol.
- Automatic resume, completed-symbol skipping and configurable retries.
- Persistent provider-failure diagnostics and snapshot compatibility checks.
- Recovery from transient OneDrive locks and newer temporary checkpoints.

### Preserved

- `run_all.py` and the personal watchlist remain unchanged.
- No scoring, governed configuration, ranking, decision or portfolio change.
- Runtime market observations remain outside version control.

### Validation

- 347 automated tests passed.
- 87.59% production coverage overall.

## PR-030A — Reproducible research-universe expansion

### Added

- Dated 503-security S&P 500 research snapshot, separate from the watchlist.
- Standard-library constituent-table parser and explicit refresh command.
- Yahoo symbol normalization with original symbols retained.
- Deterministic batch partitioning for later checkpointed collection.
- Source attribution, refresh governance and survivorship-bias boundary.

### Preserved

- Normal `run_all.py` executions still process only the personal watchlist.
- No provider burst, scoring, ranking, decision or portfolio behavior change.

### Validation

- 340 automated tests passed.
- 88.05% production coverage overall.
- Canonical snapshot pinned at 503 unique Yahoo-compatible symbols across 11
  sectors as of 2026-07-13.

## PR-029 — Robust analytical ranking

### Added

- Market, sector and candidate ordinal ranks over existing Atlas scores.
- Explicit data-confidence, missing-score, universe and Deal Breaker safeguards.
- Conditional `output/ranking_report.json` pipeline output.
- Canonical ranking policy and deterministic regression tests.

### Preserved

- No new composite score or weighting model.
- No scoring, threshold, Deal Breaker or decision change.
- Ranking remains limited to the configured watchlist.

### Validation

- 334 automated tests passed.
- 88.09% production coverage overall.
- Operational run produced four research candidates from six analyzed
  companies; this is an analytical shortlist, not a model portfolio or trade
  recommendation.

## PR-028 — Market Mapper pipeline integration

### Added

- Yahoo asset-type and average-volume metadata.
- Conditional `output/universe_report.json` generation in `run_all.py`.
- Universe policy, coverage and exclusions in Dashboard `market`.
- Focused provider-schema, serialization, pipeline and Dashboard tests.

### Preserved

- Eligibility is diagnostic and does not remove companies from scoring.
- No scoring weight, threshold, Deal Breaker or decision change.

### Validation

- 324 automated tests passed.
- 87.94% production coverage overall.
- Operational run completed with 6 analyzed, 5 eligible and 100% required-data
  coverage; BUD was explicitly excluded only from universe eligibility because
  its reported domicile is Belgium.

## PR-027 — Market Universe and Analytical Method Contract

### Added

- Canonical `config/universe.yaml` research policy.
- Immutable universe policy, member and report domain contracts.
- Pure eligibility evaluation with coverage, duplicate and standardized
  exclusion reporting.
- Analytical roadmap from market mapping through shadow-portfolio validation.

### Preserved

- No provider or main-pipeline integration.
- No scoring weight, threshold, Deal Breaker or decision change.

### Validation

- 320 automated tests passed.
- 87.96% production coverage overall with the 80% CI floor preserved.

## Claude Code project handoff

### Added

- Root `CLAUDE.md` importing the canonical Atlas rules and current handoff.
- Windows opening, validation and safe parallel-work instructions.
- Ignore rule for machine-local Claude Code settings.

## 1.2.0 — Outcome Analytics release

### Consolidated

- Completed the v1.1 Integrated Portfolio Intelligence milestone.
- Completed the v1.2 Outcome Analytics milestone through PR-019.1–PR-019.6.
- Aligned `VERSION`, README, roadmap, backlog, feature status and release notes.
- Established v2.0 Platform as the next planned milestone.
- Made Health Check status output compatible with Windows consoles that use a
  legacy code page.

### Validation

- 271 automated tests passed.
- 87.28% production coverage overall with an enforced 80% CI floor.

## PR-019.6 — Outcome reports and presentation integration

### Added

- Machine-readable `outcome_report.json` generated by the main pipeline.
- Conditional Outcome Summary, Calibration and Attribution Excel worksheets.
- Morning Brief outcome section with explicit insufficient-sample behavior.
- Serialization, workbook, rendering and pipeline regression tests.

### Validation

- 269 automated tests passed.
- 87.31% production coverage overall.

## PR-019.5 — Factor, rule and Deal Breaker attribution

### Added

- Decision-time persistence of Business, Valuation, Financial and Timing scores.
- Named Deal Breaker persistence with additive migration for existing databases.
- Factor performance attribution by horizon and score band.
- Final-decision attribution by horizon.
- Named Deal Breaker attribution with an explicit no-Deal-Breaker baseline.
- Migration, persistence and analytical-methodology regression tests.

### Safety

- Attribution is descriptive and does not claim causality.
- No factor weight, Deal Breaker, score or decision is changed.

### Validation

- 264 automated tests passed.
- 87.32% production coverage overall.

## PR-019.4 — Hit rate and score calibration

### Added

- Joined analytical dataset from immutable decision snapshots and results.
- Directional hit rate overall and by evaluation horizon.
- Explicit exclusion of HOLD and WATCH from directional accuracy.
- Configurable strict success threshold.
- Opportunity and Conviction calibration by horizon and score bucket.
- Serializable Outcome Analytics report and console hit-rate summary.
- Methodology, validation and pipeline regression tests.

### Safety

- Analytics is descriptive and does not modify scores, weights, thresholds or
  decisions.
- Calibration keeps horizons separate and reports sample counts.

### Validation

- 262 automated tests passed.
- 87.24% production coverage overall.

## PR-019.3 — Horizon return evaluation

### Added

- Immutable `OutcomeResult` with due date, evaluation lag and price return.
- Additive `outcome_results` SQLite table keyed by decision, symbol and horizon.
- Evaluation of matured decisions using current-cycle Atlas prices.
- Pending-horizon and missing-price visibility.
- First-observation immutability through insert-once persistence.
- Domain, repository, pipeline and orchestration regression tests.

### Methodology

- A horizon is evaluated on the first successful run at or after its due time.
- Returns are simple price returns and exclude dividends, fees, taxes and
  currency conversion.

### Validation

- 253 automated tests passed.
- 87.11% production coverage overall.

## PR-019.2 — Configurable horizons and automatic decision capture

### Added

- Configurable, normalized outcome evaluation horizons.
- Automatic `OutcomeSnapshot` creation after the normal history snapshot.
- Partial-success capture that reports symbols skipped for missing prices.
- Runtime switch to disable Outcome Analytics capture when required.
- Console summary of captured and skipped decisions.
- Pipeline, configuration, persistence and orchestration regression tests.

### Compatibility

- Capture defaults to enabled but can be disabled in `settings.json`.
- Assets without a valid price do not fail the company-analysis run.
- No future-price lookup or return calculation is introduced yet.

### Validation

- 238 automated tests passed.
- 86.85% production coverage overall.

## PR-019.1 — Outcome Snapshot foundation

### Added

- Immutable `OutcomeSnapshot` decision-time domain contract.
- Conversion from `CompanyReport` with explicit observed decision price.
- Additive `outcome_snapshots` SQLite table in the existing history database.
- Single and bulk persistence, symbol filtering and deterministic upsert behavior.
- Domain, validation, migration-compatibility and repository regression tests.
- Canonical Outcome Analytics specification.

### Compatibility

- Existing historical snapshots and public history methods remain unchanged.
- No automatic pipeline capture, future-price lookup or return calculation is
  introduced in this increment.

### Validation

- 225 automated tests passed.
- 86.76% production coverage overall.

## PR-018.4 — Operational coverage hardening

### Added

- Direct Health Check tests, including failure and Windows disk-space paths.
- Execution metric, stage timer, CSV persistence and console-output tests.
- Logger idempotency, handler and file-output tests.
- Technical-indicator edge-case and enrichment tests.
- `.coveragerc` with an 80% production coverage floor enforced by CI.

### Changed

- Removed one unused private Health Check helper.
- CI now executes the full suite with coverage enforcement.

### Validation

- 212 automated tests passed.
- 86.37% production coverage overall.
- 100% direct coverage for the four PR-018.4 target modules.

## PR-018.3 — Portfolio Intelligence in Morning Brief

### Added

- Executive portfolio overview with value, cash, quality, concentration and diversification.
- Largest-position, highest-conviction and highest-risk highlights.
- Explicitly advisory rebalance actions and consolidated portfolio warnings.
- Regression coverage for rendering, persistence, optional behavior and pipeline forwarding.

### Changed

- The same `PortfolioReport` now feeds JSON, Excel and Morning Brief outputs.
- Company-only Morning Brief behavior remains unchanged when no portfolio is configured.

### Validation

- 192 automated tests passed.

## Repository consolidation — 2026-07-12

- Removed patch ZIPs and expanded historical source copies already preserved by Git.
- Removed per-PR README, rollback and changelog fragments after consolidation into living documents.
- Removed local pytest cache and obsolete release-package helper files.
- Removed the unused alternate database, empty dashboard scaffold and empty data subpackages.
- Removed unreferenced legacy feature/scoring engines, leaving one executable scoring path.
- Declared the missing `yfinance` runtime dependency used by the Yahoo provider.
- Updated the canonical release notes, checklist and rollback guide.
- No production, scoring or configuration behavior changed.

## Codex transition foundation — 2026-07-12

- Added root `AGENTS.md` following the repository-instruction model used by Codex.
- Added canonical project handoff in `docs/ATLAS_CONTEXT.md`.
- Added project constitution, feature status, development, testing and Codex transition guides.
- Added GitHub Pull Request and Issue templates.
- Synchronized README, architecture, roadmap and backlog with PR-018.1/018.2 reality.
- No production scoring or runtime behavior changed.

## PR-018.2 — Portfolio Intelligence in Excel

### Added

- Conditional portfolio worksheets in historical snapshots and `latest.xlsx`.
- Portfolio-specific percentage, score and monetary formatting.
- Regression tests for Excel generation with and without a portfolio report.

### Changed

- Portfolio Intelligence now runs before Excel generation so the same
  `PortfolioReport` feeds JSON and workbook outputs.
- Duplicate portfolio declarations in `run_all.py` were removed.

### Validation

- 187 automated tests passed.

## PR-018.1 — Integrated Portfolio Pipeline

### Added

- `portfolio.pipeline` orchestration layer.
- Automatic linkage between portfolio holdings and current-cycle `CompanyReport` objects.
- Enrichment of missing holding prices and metadata from watchlist analysis.
- Consolidated `output/portfolio_report.json`.
- Optional portfolio settings in `config/settings.json`.
- End-to-end tests for the integrated portfolio pipeline.

### Changed

- `run_all.py` now executes Portfolio Intelligence when `config/portfolio.csv` exists.
- Missing portfolio input remains non-breaking and skips the optional stage.

### Validation

- 185 automated tests passed.

## Unreleased — v1.1

### PR-018.0 — Baseline and documentation synchronization

#### Added

- Repository-wide line-ending policy in `.gitattributes`.
- Current-state technical audit in `docs/ATLAS_AUDIT_CURRENT_STATUS.md`.
- Explicit integration status for Portfolio Intelligence.

#### Changed

- README now reports the correct release, v1.0.0.
- Roadmap and Backlog now reflect completed Portfolio Intelligence work.
- Architecture now documents both company and portfolio flows.
- Release notes now describe the v1.0.0 baseline and PR-018 integration track.

#### Validation

- Existing automated suite remains the regression gate.
- Baseline audit recorded 182 passing tests and 74% measured coverage.

## 1.0.0

### Added

- Portfolio import and validation.
- Holding and Portfolio domain models.
- Allocation and concentration analysis.
- Portfolio quality, ranking and advisory rebalance suggestions.
- PortfolioReport domain output and portfolio tests.

### Improved

- Derived fundamental-feature coverage.
- Momentum and shareholder-yield calculations.
- Valuation configuration ownership through `features.yaml`.
- Short-float and sector-aware Deal Breaker behavior.

## 0.9.0

### Added

- Opportunity Engine
- Conviction Engine
- Decision Policy and Decision Engine
- Investment Thesis Engine
- Historical intelligence backed by SQLite
- Trend analysis and alert generation
- Morning Brief
- Decision Analysis Excel sheet
- Reporting domain models
- Report Engine
- Health Check
- Central logger
- Execution metrics
- Automated test suite

### Changed

- Morning Brief uses `CompanyReport`.
- Decision Analysis uses domain reports.
- Runtime artifacts are excluded from Git.
- `run_all.py` delegates execution to the pipeline layer.
