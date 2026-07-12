# Release Notes — Atlas v1.0.0 / v1.1 development baseline

Atlas v1.0.0 establishes the Portfolio Intelligence domain while preserving
the complete Decision Intelligence pipeline delivered in v0.9.0.

## Highlights

### Decision and feature intelligence

Atlas produces transparent Investment, Opportunity and Conviction scores,
sector-aware Deal Breakers, structured decisions and investment theses.
Derived financial metrics now include ROIC, F-Score, Altman Z, Interest
Coverage and EV/EBIT when source data permits.

### Portfolio Intelligence domain

The release includes:

- portfolio import and validation;
- Holding and Portfolio models;
- allocation and concentration analysis;
- portfolio quality and position ranking;
- advisory-only rebalance suggestions;
- PortfolioReport domain output.

The portfolio engine is implemented and tested. Integration into `run_all.py`
and Excel is complete. Morning Brief integration is complete at PR-018.3,
including portfolio allocation, concentration, position highlights, warnings
and advisory-only rebalance actions.

### Historical and reporting intelligence

SQLite snapshots support comparisons, trends and alerts. `CompanyReport`
remains the common presentation contract used by Excel and Morning Brief.

## Validated baseline

At PR-019.2, the repository baseline validates with:

- 238 automated tests passing;
- 86.85% measured production coverage;
- 80% minimum coverage enforced in CI;
- no known functional regression;
- normalized repository line endings.

## Validation commands

```cmd
pytest
python run_all.py
```

Confirm that existing artifacts remain available, including
`output/latest.xlsx`, Morning Brief output, SQLite history, logs and metrics.
