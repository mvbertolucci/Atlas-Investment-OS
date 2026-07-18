# Backlog

## Next architectural increment — runtime boundary

- [x] Extract concrete collection and scoring application services
- [x] Extract concrete history and Outcome Analytics application service
- [x] Extract concrete intelligence application service
- [x] Extract concrete reporting application service
- [x] Extract concrete ticker-analysis application service and separate
      `TickerServices` from `RuntimeServices`
- [x] Extract `OperationalRuntimeService` for settings, Health Check, execution
      metrics and console presentation
- [x] Bind the concrete runtime service without changing CLI, output contracts
      or compatibility wrappers
- [x] Audit `run_all.py` as composition root, document the boundary and run the
      full regression/coverage gate

## Completed foundations

### Release 0.9.0 — Decision Intelligence

- [x] Decision Policy and Decision Engine
- [x] Investment Thesis Engine
- [x] Reporting domain models
- [x] Report Engine
- [x] Morning Brief domain migration
- [x] Excel domain migration
- [x] Historical intelligence and alerts

### Release 1.0.0 — Portfolio domain

- [x] Holding and Portfolio models
- [x] Portfolio CSV contract and validation
- [x] Allocation and concentration analysis
- [x] CompanyReport-to-holding enrichment
- [x] Portfolio quality and position ranking
- [x] Advisory rebalance engine
- [x] Portfolio report
- [x] Portfolio test suite

### Feature-quality track PR-017

- [x] Feature coverage audit
- [x] Derived ROIC, F-Score, Altman Z, Interest Coverage and EV/EBIT
- [x] Correct momentum and shareholder-yield calculations
- [x] Make `features.yaml` authoritative for valuation
- [x] Correct short-float deal-breaker scale
- [x] Add sector-aware Deal Breakers
- [x] Remove obsolete Confidence Score code

### Provider evidence and provenance hardening

- [x] Uniform provider timeout, exponential retries, rate limiting and typed errors
- [x] Per-field source, category, retrieval/observation/availability timestamps
- [x] Explicit present, missing, unavailable, invalid, stale and sector-not-applicable states
- [x] Immutable content-addressed raw snapshots with SHA-256 retained in history
- [x] Critical-field fallback, confirmation and conflict contract
- [x] Configure SEC Company Facts as the independent live adapter for reported
      fundamentals, with its identifying User-Agent stored only in ignored
      local configuration
- [x] Add a credential-gated Massive adapter for market cap, enterprise value,
      short interest and free float; derive `short_float` only from periods no
      more than 45 days apart
- [x] Configure a protected personal Massive API key and verify bounded live
      AAPL access to Short Interest and Float endpoints
- [x] Add the free FMP Basic adapter and confirm AAPL market cap and derived
      enterprise value against Yahoo
- [x] Combine Massive Short Interest with dated FMP Float and confirm AAPL
      `short_float` without relaxing the 45-day alignment rule
- [x] Add persistent FMP batch/cache orchestration, UTC daily-quota accounting,
      a 25-call interactive reserve, resumable prefetch and negative caching
- [x] Replace paid Massive Ratios with Basic Ticker Details for market cap and
      derive EV from Massive market cap plus SEC debt minus cash
- [x] Prefer aligned Massive native Float and use FMP Float only as fallback;
      bounded live checks passed for AAPL, AVAV and BNTX without a paid plan
- [x] Add atomic persistent/resumable Massive Ticker Details collection,
      five-call/minute protection and an ignored coverage report
- [x] Use the market-wide Massive Float endpoint with atomic page checkpoints,
      safe resumable cursors and class-symbol aliases; the live seven-page run
      covered 2,364/2,429 eligible symbols directly (97.32%) without errors
- [x] Preserve FMP as dated fallback for one additional symbol (`ET`), taking
      combined free-float availability to 2,365/2,429 (97.37%)
- [x] Classify all 64 residual free-float gaps and audit SEC
      `EntityPublicFloat`; 28 monetary values were stale, 30 absent, 3 zero and
      3 unavailable, leaving zero safe share-count conversions
- [ ] Revisit the 64 residuals only when a source supplies a dated share count
      under a comparable non-affiliate definition; do not derive it from SEC
      monetary public float or outstanding shares
- [x] Add the Massive Grouped Daily price mechanism: bounded live-verified
      Basic-plan access, `fetch_grouped_daily`, an immutable per-trade-date
      cache and a prefetch CLI. Live-verified 2026-07-16: one call matched
      2,423/2,429 eligible symbols (99.75%) — see ADR-029
- [ ] Compose `market_cap = Grouped Daily close × SEC shares_outstanding`
      (same 45-day alignment discipline as EV/short_float) into a broad,
      cached market-cap snapshot; classify the 6 unmatched Grouped Daily
      symbols instead of assuming them unavailable; retain Ticker Details for
      targeted single-symbol confirmation
- [x] Add Finnhub as a free `market_cap`/`enterprise_value` secondary source
      (60 calls/minute, no observed daily cap, vendor-computed EV in one
      call, no composition needed) and place it ahead of Massive in the live
      per-symbol reconciliation chain, ahead of FMP's 250-call/day wall
      (67/2,429 broad coverage). Live-verified end to end — see ADR-030
- [ ] Run the Finnhub broad prefetch to completion against the full
      2,429-symbol eligible universe (`providers.finnhub_prefetch --all`,
      ~45 minutes cold) and publish real broad coverage, mirroring the
      Massive Float/Grouped Daily broad runs already completed

## Completed milestone — v1.1 Integrated Portfolio Intelligence

### PR-018.0 — Baseline and documentation

- [x] Eliminate line-ending noise from the working tree
- [x] Add repository line-ending policy
- [x] Synchronize README and release version
- [x] Synchronize Roadmap and Backlog
- [x] Record the current-state technical audit

### PR-018.1 — Main-pipeline integration

- [x] Load the configured portfolio during the normal run
- [x] Match holdings to generated `CompanyReport` objects
- [x] Build `PortfolioReport` after company analysis
- [x] Preserve successful company reports when portfolio input is absent or invalid
- [x] Add integration and regression tests

### PR-018.2 — Excel integration ✅

- [x] Add Portfolio Summary sheet
- [x] Add portfolio allocation and quality worksheets
- [x] Add concentration, warnings and rebalance worksheets
- [x] Keep existing workbook sheets and contracts unchanged
- [x] Add workbook regression tests

### Codex transition foundation ✅

- [x] Add root `AGENTS.md` with durable agent instructions
- [x] Add canonical `ATLAS_CONTEXT.md` project handoff
- [x] Add project constitution, feature status and testing/development guides
- [x] Add Codex step-by-step transition guide
- [x] Add Pull Request and Issue templates
- [x] Synchronize stale portfolio integration documentation

### PR-018.3 — Morning Brief integration

- [x] Add portfolio allocation and concentration summary
- [x] Surface highest-risk and highest-conviction positions
- [x] Include advisory rebalance actions
- [x] Preserve current company-level Morning Brief sections
- [x] Add snapshot tests

### PR-018.4 — Coverage hardening

- [x] Add direct tests for Health Check
- [x] Add direct tests for execution metrics and logger behavior
- [x] Increase technical-indicator edge-case coverage
- [x] Establish and enforce the next coverage floor

### PR-018.5 — Consolidation

- [x] Review duplicate or legacy database responsibilities
- [x] Remove or migrate remaining orphaned code
- [x] Document configuration ownership and authoritative sources
- [x] Review package boundaries and public interfaces

## Completed milestone — v1.2 Outcome Analytics

- [x] Define outcome snapshot model
- [x] Configure evaluation horizons and capture decisions automatically
- [x] Track decision-to-return results over configurable horizons
- [x] Calculate hit rate and calibration metrics
- [x] Attribute results to factors, rules and Deal Breakers
- [x] Add outcome reports and regression tests

## In-progress milestone — v2.0 Platform

- [x] Define a read-only dashboard contract (`dashboard/`, see `docs/DASHBOARD_CONTRACT.md`)
- [x] Expose company, portfolio and outcome views without changing decisions
      (`run_all.py` emits `output/dados/dashboard.json`, guarded by `dashboard_enabled`)
- [x] Read-only REST API over the contract (`api/`, stdlib, no new dependency;
      see `docs/API_CONTRACT.md`). Optional later: FastAPI/OpenAPI, auth.
- [x] Read-only Python SDK (`sdk/`, HTTP or offline file transport;
      see `docs/SDK.md`)
- [x] Sell/buy priority classification, on demand (`priority/`, CLI +
      `output/dados/priority_report.json` + API `/priority` + SDK; no weight or
      sector construction -- see `docs/PRIORITY_REPORT.md`)

### Portfolio workflow

- [x] Real portfolio populated (`config/portfolio.csv`, gitignored) and
      wired to the scoring/decision pipeline
- [x] Sell-only rebalance mode (no internal reallocation) --
      `portfolio.rebalance_mode = "sell_only"` (default)
- [x] `config/watchlist.csv` (manually curated research symbols) and
      `config/portfolio.csv` (real holdings) are distinct files again --
      neither overwrites the other. A 2026-07-13 session had merged the
      real portfolio's 24 symbols directly into `watchlist.csv` to give the
      sell-only engine `CompanyReport`s to match against; corrected the same
      day: `run_all.merge_watchlist_with_portfolio` merges the two **only in
      memory**, once per run, so the analyzed/scored universe covers both
      without polluting either source file
- [x] Universe provenance: every merged row carries an `origin`
      (`portfolio` > `watchlist`, ready for a future `> universe` tier from
      the broad-market screener), propagated through
      `collect_market_data`/`build_scores` untouched. Two contract
      guarantees, both regression-tested end to end:
      - `portfolio.rebalance.build_sell_only_plan` never emits SELL/HOLD for
        a holding whose origin (verified via `Holding.origin`, filled by
        `enrich_portfolio_from_analysis` from the analyzed row) is not
        `portfolio` -- a real gap was found and fixed here: the engine
        previously trusted `Portfolio.holdings` unconditionally, with no
        defense if a caller ever built one from a non-portfolio symbol
      - `ranking.RankedCompany.already_held` (and the existing
        `priority.BuyPriorityItem.already_held`) flag every portfolio-origin
        row, so a real holding is never presented as an ordinary fresh
        candidate in `output/dados/ranking_report.json` or the buy screener

### Analytical-method priority

- [x] PR-027 Define the market-universe and analytical-method contract
- [x] PR-028 Integrate the Market Mapper and publish universe coverage
- [x] PR-029 Add robust market/sector ranking with absolute safeguards
- [x] PR-030A Add a dated, reproducible 503-security research snapshot
- [x] PR-030B Collect the expanded universe in checkpointed batches
- [x] PR-031 Build an advisory model portfolio under explicit constraints
- [x] PR-032 Define the point-in-time historical-data contract
- [x] PR-033 Implement deterministic walk-forward backtesting -- the replay
      *mechanism* (`backtesting/walk_forward.py`), proven with synthetic,
      offline fixtures. See `docs/WALK_FORWARD_BACKTEST.md`.

### Real historical data acquisition (the actual blocker for a real backtest)

- [x] `backtesting/sec_edgar.py`: SEC EDGAR XBRL -> `HistoricalObservation`,
      free/public/no-key. Conservative `available_at` convention (midnight
      UTC the day after filing). See `docs/SEC_EDGAR_DATA.md` for the full
      "what is covered / what is not" accounting.
- [x] Widened tag coverage to 15 fields (from the initial 5), verified
      against **live SEC data** for Apple Inc. (2,350 observations):
      `total_assets`, `net_income`, `total_revenue`, `current_assets`,
      `current_liabilities`, `gross_profit`, `long_term_debt`,
      `retained_earnings`, `total_liabilities`, `interest_expense`,
      `tax_provision`, `pretax_income`, `repurchase_of_stock`,
      `operating_income` (explicit EBIT proxy, not silently renamed),
      `shares_outstanding` (from the `dei` taxonomy). Multiple candidate
      tags per field are extracted and merged (not just the first with
      data), handling real cross-era tag switches (e.g. the ~2018 revenue-
      recognition tag change) -- two extra native tags added
      (`operating_cash_flow`, `cash_and_equivalents`) to support the ratio
      derivation below.
- [x] `backtesting/point_in_time_fundamentals.py`: derives the *ratios*
      `config/features.yaml` actually scores on (`gross_margin`,
      `operating_margin`, `net_margin`, `current_ratio`, `working_capital`,
      `total_equity`, `debt_to_equity`, `interest_coverage`, `roe`, `roic`)
      from the raw SEC fields -- only fills gaps, never overwrites a ratio
      already supplied. Wired into `run_walk_forward`. **Verified end to
      end against real SEC data**: derived gross margin 48.6% (Apple) /
      68.2% (Microsoft), matching each company's real historical range;
      the full walk-forward engine produced two genuinely different
      Investment Scores (52.9 / 58.9) instead of both collapsing to a
      neutral 50. Multi-period `f_score_annual` and price-dependent
      `altman_z` were completed in subsequent bounded increments.
- [x] Pair a historical price series
      (`backtesting/price_history.py`, Yahoo daily close, same
      no-look-ahead convention as SEC filings) and derive `market_cap`,
      `pe`, `pb`, `altman_z` from it (`backtesting/point_in_time_valuation.py`).
      Verified end to end against real, live data: Apple `market_cap`
      ~$4.1T / `pe` 57.4 / `pb` 38.6 / `altman_z` 10.9; Microsoft `market_cap`
      ~$3.1T / `pe` 31.4 / `pb` 7.4 / `altman_z` 8.2 -- Model Confidence rose
      from ~32.5% to 40.0% now that `valuation` factors are partially
      populated. See `docs/PRICE_HISTORY_DATA.md`.
- [x] Correct `market_cap` for stock splits before the most recent split
      (Yahoo's paired price is retroactively split-adjusted; SEC's
      `shares_outstanding` is not -- implemented through restored as-traded
      closes, explicit `StockSplitRecord` events and observed-date-aware
      cumulative share adjustment; see docs/PRICE_HISTORY_DATA.md)
- [x] Derive `f_score_annual` from two complete, consecutive 10-K filings
      visible at the decision cutoff; preserve amendments, reject partial or
      non-consecutive comparisons and normalize shares for intervening splits
- [x] Extend valuation coverage: `enterprise_value`, `ev_ebit`,
      `free_cash_flow`, `fcf_yield` and `shareholder_yield`
      (`backtesting/point_in_time_valuation.py`), each mirroring the exact
      formula `analytics/mapper.py` already uses live. Two new SEC EDGAR
      tags added (`capital_expenditures`, `dividends_paid`), same
      collector/mapping mechanism as the existing 15 fields. Remaining
      gaps need a new data source, not just a tag addition: `forward_pe`/
      `peg` (analyst estimates) and `ev_ebitda` (the live pipeline has no
      formula of its own to mirror -- it passes through Yahoo's
      `enterpriseToEbitda` directly)
- [x] Derive the `timing` factor family (`rsi_14`, `momentum_3m/6m/12m`,
      `distance_52w_high`) from the same paired price series
      (`backtesting/point_in_time_timing.py`, wired into
      `walk_forward.replay_decision_batch`). Reconstructs a continuous,
      split-adjusted close series per symbol at each cutoff -- mirrors
      `analytics/indicators.py`'s exact formulas and trading-day windows.
      Proven that forward/reverse splits create no artificial momentum and
      that a not-yet-known split or a future price never leaks into an
      earlier replay. `target_upside` remains unbuilt (needs a genuine
      point-in-time analyst-target source).
- [x] Checkpointed multi-ticker collector
      (`backtesting/sec_edgar_collector.py`, mirroring
      `universe/collector.py`'s resumable design). Verified against a real
      batch of Atlas's actual watchlist: `ASML`/`AVAV`/`BNTX` collected
      successfully; `BEEF3.SA` (B3-only, no US SEC registration) correctly
      failed explicitly with "CIK não encontrado" -- confirms the hard
      boundary that non-SEC-registered tickers can never be covered by
      this source.
- [ ] Historical index membership (still unresolved -- no free source, see
      `docs/UNIVERSE_SOURCES.md`) and delisting records with return
      treatment
- [ ] Run the walk-forward engine against the resulting real dataset once
      it is usable end to end
- [ ] PR-034 Add portfolio performance and risk validation
      - [x] Deterministic validation core for total/benchmark return,
        volatility, drawdown, turnover, explicit costs and position
        concentration; incomplete periods suppress aggregate metrics
      - [x] Versioned local JSON runner with mandatory provenance, CLI and
        explicit sector-concentration coverage
      - [x] Build point-in-time model-portfolio targets from the same governed
        scoring/universe/ranking path; retain coverage gaps and config hashes
      - [x] Govern next-session-open execution and convert targets to dated
        rebalances only when every attributed opening price is present
      - [x] Add a versioned observed-session/open-price artifact and pure
        Yahoo-bar adapter with DST and split-unit handling
      - [x] Add a versioned, source-attributed dividend-inclusive
        total-return adapter (`backtesting/total_return_evidence.py`):
        compounds `(Close+Dividend)/previous_close` day over day from
        already-acquired Yahoo bars into the `AssetPeriodReturn` rows the
        validation runner already consumes; works for both holdings and the
        benchmark; a `DelistingRecord` overrides only the one period
        containing `last_trade_on` (`zero` forces -100%, `cash` combines the
        compounded multiplier with `cash_proceeds`, `successor`/`unresolved`
        are both reported `unresolved` -- never a fabricated successor
        value); missing evidence is omitted, never invented
      - [ ] Run bounded real acquisition for reference/selected-symbol bars
      - [ ] Acquire real `DelistingRecord` terminal-event evidence and run
        the new total-return adapter against a broad real dataset (the
        adapter and its versioned artifact are implemented; no broad real
        artifact is committed or collected yet)
      - [x] Add per-sector return contribution (`target_weight ×
        asset_return`, summed per sector) to each complete validation
        period, reusing the existing `PortfolioRebalance.sectors` mapping --
        `null` under the same absent/partial-coverage rule as `sector_hhi`;
        values always sum to exactly `gross_return`
      - [x] Add weighted-average factor exposure (`business`/`valuation`/
        `financial`/`timing`, 0-100) to `PortfolioRebalance` and each
        complete validation period. `backtesting/historical_portfolio.py`
        reads it straight from the governed scoring pass at each cutoff --
        not recomputed, not a new input. Composition/tilt only, not a
        return decomposition; `null` unless every held symbol has the same
        factor set
      - [ ] A regression-based factor-*return* decomposition (the
        finance-standard sense of "factor contribution") remains open --
        needs a statistical methodology to validate and document, a
        separate, larger increment than the exposure summary above
      - [ ] Run broad real validation and report coverage
- [ ] PR-035 Track a prospective shadow portfolio
- [ ] PR-036 Calibrate only from versioned out-of-sample evidence

### Second screener: broad US market (small caps)

A separate screener from the S&P 500 one, requested to also cover small
caps under an explicit minimum-entry parameter. Distinct config, snapshot,
checkpoint and batch size throughout -- the S&P 500 screener is unchanged.

- [x] Source: NASDAQ Trader symbol directory (`nasdaqlisted.txt` +
      `otherlisted.txt`) -- the closest free, public, comprehensive US-market
      listing, since Russell 3000/Wilshire 5000 have no free constituent list
- [x] Governed policy `config/universe_market.yaml`: USD 300 million minimum
      market cap (a genuine small-cap floor, vs. the S&P 500 screener's USD 1
      billion, which is really a mid-cap-and-up floor)
- [x] `universe.collector` gains `--market` (own snapshot/state/batch-size,
      via `config/settings.json`) and `--snapshot` overrides
- [x] Default batch advancement honors the configured retry budget: a
      permanently failing ticker remains visible in the checkpoint but cannot
      pin automatic collection to the same batch forever; explicit
      `--batch-number` remains available for reprocessing
- [x] `portfolio.model_portfolio` (`build_from_collection`/`main`) accepts
      `--universe-policy`/`--ranking-policy`/`--model-portfolio-policy` and
      `--label`, so ranking/model-portfolio can run over this screener with
      distinct output filenames, not just the S&P 500 one (defaults
      unchanged -- see `docs/MODEL_PORTFOLIO.md`)
- [x] Run the actual collection: 6,959 observations from the 7,093-symbol
      snapshot; 134 exhausted provider failures retained explicitly
- [x] Run ranking / `portfolio.model_portfolio --universe-policy
      config/universe_market.yaml --label market --allow-exhausted-failures`:
      2,429 eligible companies; the evidence-quality rerun yields 794
      safeguarded candidates and a constrained
      20-position advisory portfolio; ignored `*_market` artifacts generated

### Third screener: US-listed ADRs

Same USD 300 million floor as the broad-market screener. No new data
source or collection -- ADRs already trade on US exchanges, so they are
already in the broad-market collection; what excluded them was the country
policy, not missing data.

- [x] `UniversePolicy` gains `excluded_countries` and an `allowed_countries`
      `"*"` wildcard (additive, backward-compatible; pinned by a governance
      test that the two existing screeners are unaffected)
- [x] Governed policy `config/universe_adr.yaml`: same USD 300 million floor,
      `allowed_countries: ["*"]`, `excluded_countries: [United States]`
- [x] Run `portfolio.model_portfolio --universe-policy
      config/universe_adr.yaml --label adr` against the broad-market
      collection: 501 eligible companies, 219 safeguarded candidates and a
      distinct constrained 20-position advisory portfolio; ignored `*_adr`
      artifacts generated

### Deferred platform effects

- [ ] Scheduling — resume after the analytical method is validated
- [ ] Notifications — requires an explicit external channel/config decision
- [ ] AI assistant — requires an explicit LLM provider/key decision
