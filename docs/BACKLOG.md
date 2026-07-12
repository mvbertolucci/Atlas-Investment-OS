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

## Active milestone — v1.1 Integrated Portfolio Intelligence

### PR-018.0 — Baseline and documentation

- [x] Eliminate line-ending noise from the working tree
- [x] Add repository line-ending policy
- [x] Synchronize README and release version
- [x] Synchronize Roadmap and Backlog
- [x] Record the current-state technical audit

### PR-018.1 — Main-pipeline integration

- [ ] Load the configured portfolio during the normal run
- [ ] Match holdings to generated `CompanyReport` objects
- [ ] Build `PortfolioReport` after company analysis
- [ ] Preserve successful company reports when portfolio input is absent or invalid
- [ ] Add integration and regression tests

### PR-018.2 — Excel integration ✅

- [ ] Add Portfolio Summary sheet
- [ ] Add Holdings Analysis sheet
- [ ] Add Concentration and Rebalance sections
- [ ] Keep existing workbook sheets and contracts unchanged
- [ ] Add workbook regression tests

### PR-018.3 — Morning Brief integration

- [ ] Add portfolio allocation and concentration summary
- [ ] Surface highest-risk and highest-conviction positions
- [ ] Include advisory rebalance actions
- [ ] Preserve current company-level Morning Brief sections
- [ ] Add snapshot tests

### PR-018.4 — Coverage hardening

- [ ] Add direct tests for Health Check
- [ ] Add direct tests for execution metrics and logger behavior
- [ ] Increase technical-indicator edge-case coverage
- [ ] Establish and enforce the next coverage floor

### PR-018.5 — Consolidation

- [ ] Review duplicate or legacy database responsibilities
- [ ] Remove or migrate remaining orphaned code
- [ ] Document configuration ownership and authoritative sources
- [ ] Review package boundaries and public interfaces

## Next milestone — v1.2 Outcome Analytics

- [ ] Define outcome snapshot model
- [ ] Track decision-to-return results over configurable horizons
- [ ] Calculate hit rate and calibration metrics
- [ ] Attribute results to factors, rules and Deal Breakers
- [ ] Add outcome reports and regression tests
