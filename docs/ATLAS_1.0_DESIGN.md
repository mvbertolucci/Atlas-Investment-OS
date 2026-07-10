# Atlas Investment OS v1.0 — Architecture Design

## Objective

Transform Atlas from a company analysis platform into a portfolio decision platform.

## Product question

Atlas v1.0 must answer:

> What should I do with my portfolio, and why?

## Scope

### Included

- Portfolio import
- Holdings domain model
- Portfolio domain model
- Allocation analysis
- Concentration analysis
- Portfolio quality analysis
- Position ranking
- Rebalance suggestions
- Portfolio report
- Portfolio Morning Brief

### Excluded

- Automatic trading
- Broker integration
- Mobile application
- Generative AI assistant
- Full mean-variance optimization
- Tax optimization
- Real-time streaming

## Domain model

### Holding

Represents one position.

Fields:

- symbol
- quantity
- average_price
- current_price
- market_value
- portfolio_weight
- sector
- industry
- country
- currency
- company_report

### Portfolio

Represents the complete portfolio.

Fields:

- name
- cash
- holdings
- total_market_value
- total_value
- currency
- created_at

### AllocationSnapshot

Represents portfolio allocation.

Fields:

- by_symbol
- by_sector
- by_country
- by_currency
- cash_weight

### PortfolioRisk

Represents portfolio-level risk.

Fields:

- concentration_score
- diversification_score
- largest_position_weight
- top_5_weight
- sector_concentration
- country_concentration
- currency_concentration
- warnings

### RebalanceAction

Represents one suggested action.

Fields:

- symbol
- action
- current_weight
- target_weight
- target_value
- trade_value
- reason
- priority

### RebalancePlan

Represents the complete rebalance proposal.

Fields:

- actions
- required_cash
- released_cash
- estimated_turnover
- warnings

### PortfolioReport

Represents the presentation model.

Fields:

- portfolio_name
- total_value
- cash
- holdings_count
- average_investment_score
- average_opportunity_score
- average_conviction_score
- concentration_score
- diversification_score
- top_positions
- rebalance_actions
- observations

## Architecture

```text
Market Data
    ↓
Current Atlas Pipeline
    ↓
CompanyReport
    ↓
Holding
    ↓
Portfolio
    ↓
Allocation Engine
    ↓
Risk Engine
    ↓
Rebalance Engine
    ↓
PortfolioReport
    ↓
Excel / Morning Brief / Markdown / API
```

## Package structure

```text
portfolio/
├── __init__.py
├── models.py
├── loader.py
├── allocation.py
├── concentration.py
├── quality.py
├── rebalance.py
├── report_engine.py
└── validators.py

tests/
├── test_portfolio_models.py
├── test_portfolio_loader.py
├── test_portfolio_allocation.py
├── test_portfolio_concentration.py
├── test_portfolio_quality.py
├── test_portfolio_rebalance.py
└── test_portfolio_report_engine.py
```

## Core rules

1. Portfolio logic must consume `CompanyReport`.
2. DataFrames remain at ingestion and export boundaries.
3. Rebalance output is advisory, never executable.
4. Every recommendation must include a reason.
5. Missing prices or reports must produce warnings, not silent defaults.
6. Cash is a first-class portfolio component.
7. All weights must sum to 100% within tolerance.
8. Target weights must respect configured limits.

## Configuration

Proposed file:

```text
config/portfolio.yaml
```

Example:

```yaml
base_currency: BRL

limits:
  max_position_weight: 0.20
  max_sector_weight: 0.35
  max_country_weight: 0.60
  minimum_cash_weight: 0.05

rebalance:
  minimum_trade_value: 500
  tolerance: 0.02
  allow_sells: true

quality_weights:
  investment: 0.35
  opportunity: 0.25
  conviction: 0.25
  decision_confidence: 0.15
```

## Definition of done

Atlas v1.0 is complete when:

- A portfolio can be loaded from CSV.
- Holdings are validated.
- Current weights are calculated.
- Allocation by symbol, sector and country is available.
- Concentration warnings are generated.
- Portfolio quality score is calculated.
- Rebalance actions are suggested.
- Portfolio report is generated.
- Portfolio Morning Brief is generated.
- Tests pass.
- Documentation is complete.
