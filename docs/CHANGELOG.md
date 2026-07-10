# Changelog

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

- Morning Brief now uses `CompanyReport`.
- Decision Analysis now uses domain reports.
- Runtime artifacts are excluded from Git.
- `run_all.py` delegates execution to the pipeline layer.

### Compatibility

- Existing scoring and reporting interfaces remain available.
- Existing Excel and Morning Brief workflows remain supported.
