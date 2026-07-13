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

### Market-universe layer

- `config/universe.yaml`
- `universe/models.py`
- `universe/pipeline.py`
- `universe/sources.py`
- `universe/collector.py`

The universe layer is an eligibility boundary over collected provider data.
Yahoo supplies `quote_type` and liquidity metadata; `run_all.py` evaluates the
configured policy, writes `output/universe_report.json` and forwards the same
report to Dashboard `market`. It reports coverage and standardized exclusions
without filtering scoring or changing a decision.
The source module parses a dated public constituent table into a committed
research snapshot and provides deterministic batch boundaries. The collector
processes one boundary at a time, persists each result atomically and resumes
without requesting completed symbols again. Both network actions are explicit;
`run_all.py` continues to process the personal watchlist.

### Analytical-ranking layer

- `config/ranking.yaml`
- `ranking/models.py`
- `ranking/pipeline.py`
- `ranking/report.py`

The ranking orders existing Investment, Opportunity and Conviction outputs at
market and sector level. Candidate safeguards reuse Universe eligibility,
Confidence Score and governed Deal Breakers; no new score is calculated.

### Advisory model-portfolio layer

- `config/model_portfolio.yaml`
- `portfolio/model_portfolio.py`

The model builder consumes a complete local collection, reuses the executable
normalization/scoring/universe/ranking path and constructs an equal-weight
portfolio under pinned position, sector, cash and initial-turnover constraints.
It writes ignored research artifacts and remains separate from `run_all.py` and
the user's real `config/portfolio.csv`.

### Historical-validation contract layer

- `backtesting/point_in_time.py`
- `docs/POINT_IN_TIME_DATA.md`

The point-in-time layer defines the immutable evidence boundary for future
walk-forward validation. It filters observations by source availability,
preserves both the latest value and complete available revision history,
reconstructs constituent membership from
non-overlapping historical intervals, aligns price/share units through explicit
split events and requires terminal treatment for delisted securities. The
walk-forward mechanism derives single-period ratios, two-period Piotroski
F-Score and partial valuation before replaying governed decisions. It does not
calculate portfolio returns; those remain a PR-034 responsibility.

### Outcome layer

- `outcomes/models.py`
- `outcomes/pipeline.py`
- `outcomes/analytics.py`
- `outcomes/report.py`
- `storage/history_db.py` (`outcome_snapshots` and `outcome_results` tables)

The main pipeline captures outcome snapshots after the company decision is
available. On later runs, matured horizons use the current valid Atlas price to
create an immutable result. The first observation on or after the due date wins,
and evaluation lag remains explicit. Analytics joins immutable decisions and
results to calculate directional hit rate and score calibration by horizon.
Attribution uses the same joined dataset to relate returns to factor-score
bands, final decision rules and named Deal Breakers.
The main pipeline serializes the analytical contract to JSON and passes the
same report object to conditional Excel worksheets and Morning Brief rendering.

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
4. `config/features.yaml` is the authoritative feature definition;
   `config/universe.yaml` is the authoritative research-universe policy.
5. Runtime output, logs and local databases remain outside version control.
6. New integrations must preserve existing public interfaces and regression
   tests unless a migration is explicitly documented.
