# Release Notes — Atlas v1.2.0

Atlas v1.2.0 completes Outcome Analytics and the integration of Portfolio
Intelligence while preserving the Decision Intelligence pipeline delivered in
earlier releases.

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

### Outcome Analytics

Atlas now captures immutable decision snapshots, evaluates returns over
configurable horizons and reports directional hit rate, score calibration and
factor, decision-rule and Deal Breaker attribution.

The same analytical contract is available through:

- `output/outcome_report.json`;
- conditional Outcome worksheets in Excel;
- a concise Outcome Analytics section in Morning Brief.

Outcome Analytics is descriptive. It does not modify scoring weights,
thresholds, Deal Breakers or final decisions.

## Validated baseline

The v1.2.0 / PR-019.6 repository baseline validates with:

- 271 automated tests passing;
- 87.28% measured production coverage;
- 80% minimum coverage enforced in CI;
- no known functional regression;
- normalized repository line endings.

## Validation commands

```cmd
pytest
python run_all.py
```

Confirm that existing artifacts remain available, including
`output/latest.xlsx`, Morning Brief output, Outcome JSON, SQLite history, logs
and metrics.
