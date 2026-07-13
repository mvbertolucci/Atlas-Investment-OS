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
- [ ] Expose company, portfolio and outcome views without changing decisions
      (wire `run_all.py` to emit `output/dashboard.json`)
- [ ] Add scheduling and notifications only after the dashboard boundary is stable
- [ ] Keep API, SDK and AI assistant as separate increments
