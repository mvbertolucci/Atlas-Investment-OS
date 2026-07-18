# Testing Guide

## Standard command

```bash
python -m pytest tests -q \
  --cov=. \
  --cov-config=.coveragerc \
  --cov-report=term-missing \
  --cov-fail-under=80
```

The GitHub Actions workflow executes the tests on Python 3.12.

## Policy

- Behavioral changes require tests.
- Bug fixes require a regression test that fails before the fix.
- Tests must be deterministic and must not require Yahoo or another live service.
- Use fixtures or monkeypatching for external providers and filesystem boundaries.
- Do not lower assertion quality or delete tests merely to restore green CI.

## Test layers

1. **Unit:** factors, policies, validators, calculations and render helpers.
2. **Contract:** output columns, workbook sheets, JSON shape and domain interfaces.
3. **Integration:** pipeline composition with controlled local inputs.
4. **Regression:** previously corrected financial semantics and edge cases.

## Coverage baseline

Current historical-data baseline validates:

- 905 automated tests;
- 90.39% measured production coverage;
- 100% direct coverage for Health Check, execution metrics, logger and
  technical indicators;
- an enforced 80% floor in GitHub Actions through `.coveragerc`.

Tests and virtual-environment files are excluded from the production coverage
calculation. The floor must not be lowered merely to make CI pass.
