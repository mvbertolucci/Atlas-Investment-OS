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

The portfolio flow is integrated into the company pipeline through
`portfolio/pipeline.py` and the same `PortfolioReport` is exported to JSON,
conditional Excel sheets and the Morning Brief.

## Layers

### Data layer

- `providers/`
- `analytics/mapper.py`
- `analytics/fundamentals.py`
- `analytics/indicators.py`

### Feature and scoring layer

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
- `portfolio/pipeline.py`

### Historical layer

- `storage/history_db.py`
- `analytics/history.py`
- `analytics/alerts.py`
- `reports/history_report.py`

### Outcome layer

- `outcomes/models.py`
- `storage/history_db.py` (`outcome_snapshots` table)

Outcome snapshots preserve the decision-time state. Future-price evaluation and
derived return metrics remain separate later stages.

### Operational layer

- `health/`
- `metrics/`
- `atlas_logger.py`
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
