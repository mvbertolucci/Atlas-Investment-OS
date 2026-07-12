# PR-018.1 — Integrated Portfolio Pipeline

## Objective

Connect the existing Portfolio Intelligence domain to the principal Atlas
execution flow without changing company scoring or breaking executions that do
not yet have a real portfolio file.

## Changes

- Added `portfolio/pipeline.py` as the orchestration layer for the portfolio
  engines.
- Connected holdings to the `CompanyReport` objects produced by the current
  analysis cycle.
- Added fallback enrichment for missing current prices, sector, industry and
  country using the analyzed watchlist data.
- Connected Allocation, Concentration, Portfolio Quality, Rebalance and
  Portfolio Report engines in one deterministic flow.
- Added `output/portfolio_report.json` as the first integrated portfolio
  artifact.
- Added portfolio configuration keys to `config/settings.json`.
- Connected the optional stage to `run_all.py`.

## Activation

Copy the example file and replace its contents with the real portfolio:

```cmd
copy config\portfolio.example.csv config\portfolio.csv
```

The following settings are available:

```json
{
  "portfolio_path": "config/portfolio.csv",
  "portfolio_name": "Atlas Portfolio",
  "portfolio_cash": 0.0,
  "portfolio_currency": "BRL"
}
```

When `config/portfolio.csv` is absent, the Atlas logs the skip and completes the
existing company-analysis pipeline normally.

## Generated artifact

```text
output/portfolio_report.json
```

The JSON contains executive summary, allocation, concentration, portfolio
quality, rebalance actions and warnings.

## Validation

```text
185 tests passed
0 failures
```

## Next PR

PR-018.2 — Add Portfolio Intelligence worksheets to `latest.xlsx` and the
historical workbook.
