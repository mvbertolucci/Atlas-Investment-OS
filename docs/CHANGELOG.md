# Changelog

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
