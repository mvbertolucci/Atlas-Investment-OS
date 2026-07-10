# Architecture

## Pipeline

```text
Yahoo Provider
      ↓
Normalization and Validation
      ↓
Factor Engine
      ↓
Business / Valuation / Financial / Timing
      ↓
Investment Score
      ↓
Deal Breakers
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
Excel / Morning Brief / future API and Dashboard
```

## Layers

### Data layer

- `providers/`
- `analytics/mapper.py`
- `analytics/validator.py`

### Scoring layer

- `factors/`
- `scoring/`
- `models/`

### Decision layer

- `decision/policy.py`
- `decision/engine.py`
- `decision/thesis.py`

### Domain and reporting layer

- `reports/report_models.py`
- `reports/report_engine.py`
- `reports/morning_brief.py`
- `reports/excel.py`

### Historical layer

- `storage/history_db.py`
- `analytics/history.py`
- `analytics/alerts.py`
- `reports/history_report.py`

### Operational layer

- `health/`
- `metrics/`
- `atlas_logger.py`
- `pipeline/runner.py`

## Architectural rule

Presentation components should consume domain objects such as
`CompanyReport` whenever possible, rather than reading the raw scoring
DataFrame directly.
