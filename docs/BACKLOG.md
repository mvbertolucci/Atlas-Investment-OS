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
- [ ] PR-033 Implement deterministic walk-forward backtesting
- [ ] PR-034 Add portfolio performance and risk validation
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
- [ ] Run the actual collection (not started -- expected several thousand
      eligible names, materially slower/more rate-limit-prone than the
      503-name S&P 500 screener; see `docs/UNIVERSE_SOURCES.md`)
- [ ] Run ranking / `portfolio.model_portfolio` over the broad-market
      collection once it completes (deliberately deferred)

### Deferred platform effects

- [ ] Scheduling — resume after the analytical method is validated
- [ ] Notifications — requires an explicit external channel/config decision
- [ ] AI assistant — requires an explicit LLM provider/key decision
