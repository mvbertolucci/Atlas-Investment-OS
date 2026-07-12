# PR-018.2 — Portfolio Intelligence in Excel

## Objective

Add the Portfolio Intelligence outputs to both `output/latest.xlsx` and the
historical Excel snapshot, while preserving the existing workbook when no
portfolio is configured.

## Changes

- `reports.excel.write_latest_and_history` now accepts an optional
  `PortfolioReport`.
- `run_all.py` now builds the optional portfolio report before generating the
  Excel workbook and passes the same domain object to the reporting layer.
- Added the following conditional worksheets:
  - `Portfolio Summary`
  - `Portfolio Allocation`
  - `Portfolio Concentration`
  - `Portfolio Quality`
  - `Portfolio Rebalance`
  - `Portfolio Warnings`
- Added portfolio-specific formatting for percentages, scores, monetary values,
  headers and gridline visibility.
- Removed duplicate portfolio imports, constants and function definitions found
  in `run_all.py`.

## Compatibility

When `config/portfolio.csv` is absent, the Excel workbook keeps its previous
structure and no portfolio worksheet is created.

## Validation

```text
187 tests passed
0 failures
```

## Next PR

PR-018.3 — Add Portfolio Intelligence to the Morning Brief.
