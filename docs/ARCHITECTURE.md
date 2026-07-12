# Architecture

## Integrated company-analysis pipeline

```text
Yahoo Provider
      ↓
Normalization and Validation
      ↓
Feature and Factor Engines
      ↓
Business / Valuation / Financial / Timing
      ↓
Investment Score
      ↓
Deal Breakers and Risk Penalties
      ↓
Opportunity Score
      ↓
Conviction Score
      ↓
Decision Engine
      ↓
Investment Thesis
      ↓
Report Engine
      ↓
CompanyReport
      ↓
History / Alerts / Excel / Morning Brief
```

## Portfolio Intelligence domain

```text
Portfolio CSV
      ↓
Loader and Validators
      ↓
Holding / Portfolio Models
      ↓
CompanyReport Enrichment
      ↓
Allocation / Concentration / Quality
      ↓
Ranking / Advisory Rebalance
      ↓
PortfolioReport
```

The portfolio flow is implemented as a tested domain. PR-018.1 will connect it
to the integrated company pipeline; PR-018.2 and PR-018.3 will connect it to
Excel and Morning Brief.

## Layers

### Data layer

- `providers/`
- `analytics/mapper.py`
- `analytics/validator.py`

### Feature and scoring layer

- `analytics/feature_engine.py`
- `factors/`
- `scoring/`
- `models/`
- `config/features.yaml`

### Decision layer

- `decision/policy.py`
- `decision/engine.py`
- `decision/thesis.py`

### Company reporting layer

- `reports/report_models.py`
- `reports/report_engine.py`
- `reports/morning_brief.py`
- `reports/excel.py`

### Portfolio layer

- `portfolio/loader.py`
- `portfolio/models.py`
- `portfolio/allocation.py`
- `portfolio/concentration.py`
- `portfolio/quality.py`
- `portfolio/rebalance.py`
- `portfolio/report.py`
- `portfolio/validators.py`

### Historical layer

- `storage/history_db.py`
- `analytics/history.py`
- `analytics/alerts.py`
- `reports/history_report.py`

### Operational layer

- `health/`
- `metrics/`
- `atlas_logger.py`
- `pipeline/`
- `run_all.py`

## Architectural rules

1. Presentation components should consume domain objects such as
   `CompanyReport` and `PortfolioReport`, not raw provider payloads.
2. Rebalance output is advisory only; Atlas must not execute trades.
3. Cash is represented as a portfolio asset where supported by the portfolio
   contract.
4. `config/features.yaml` is the authoritative valuation-feature definition.
5. Runtime output, logs and local databases remain outside version control.
6. New integrations must preserve existing public interfaces and regression
   tests unless a migration is explicitly documented.
