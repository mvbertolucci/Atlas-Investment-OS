# Backlog

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
      (`run_all.py` emits `output/dashboard.json`, guarded by `dashboard_enabled`)
- [x] Read-only REST API over the contract (`api/`, stdlib, no new dependency;
      see `docs/API_CONTRACT.md`). Optional later: FastAPI/OpenAPI, auth.
- [x] Read-only Python SDK (`sdk/`, HTTP or offline file transport;
      see `docs/SDK.md`)
- [x] Sell/buy priority classification, on demand (`priority/`, CLI +
      `output/priority_report.json` + API `/priority` + SDK; no weight or
      sector construction -- see `docs/PRIORITY_REPORT.md`)

### Portfolio workflow

- [x] Real portfolio populated (`config/portfolio.csv`, gitignored) and
      wired to the scoring/decision pipeline via `config/watchlist.csv`
- [x] Sell-only rebalance mode (no internal reallocation) --
      `portfolio.rebalance_mode = "sell_only"` (default)

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
      - [ ] Build dated model portfolios from walk-forward decisions
      - [ ] Acquire complete total-return/benchmark/delisting evidence
      - [ ] Add sector and factor contribution without look-ahead
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
- [ ] Run the actual collection (not started -- expected several thousand
      eligible names, materially slower/more rate-limit-prone than the
      503-name S&P 500 screener; see `docs/UNIVERSE_SOURCES.md`)
- [ ] Run ranking / `portfolio.model_portfolio --universe-policy
      config/universe_market.yaml --label market` over the broad-market
      collection once it completes (deliberately deferred; the command
      itself is ready)

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
- [ ] Run `portfolio.model_portfolio --universe-policy
      config/universe_adr.yaml --label adr` against the broad-market
      collection once collected (deliberately deferred, same as the
      broad-market screener's own ranking step; the command itself is
      ready)

### Deferred platform effects

- [ ] Scheduling — resume after the analytical method is validated
- [ ] Notifications — requires an explicit external channel/config decision
- [ ] AI assistant — requires an explicit LLM provider/key decision
