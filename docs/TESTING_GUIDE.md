# Testing Guide

## Standard command

```bash
python -m pytest tests -q
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

## Coverage direction

The last audited global coverage was 74% before PR-018.1/018.2. PR-018.4 must establish a new measured baseline and enforce a conservative floor only after uncovered operational paths receive direct tests.

Priority gaps:

- `health/health_check.py`;
- `metrics/execution.py`;
- logger behavior;
- technical-indicator edge cases;
- Morning Brief branches;
- legacy database modules under consolidation review.
