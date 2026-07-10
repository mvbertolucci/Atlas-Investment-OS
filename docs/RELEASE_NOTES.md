# Release Notes — Atlas v0.9.0

Atlas v0.9.0 introduces the complete Decision Intelligence layer.

## Highlights

### Decision Engine

Atlas interprets Opportunity, Conviction, risk penalties and Deal Breakers
to produce a structured decision.

### Investment Thesis

Each company receives:

- Investment Thesis
- Strengths
- Risks
- Catalysts
- Suggested Action

### Historical Intelligence

SQLite snapshots enable comparisons, trends and alerts over time.

### Reporting architecture

`CompanyReport` becomes the common domain model for presentation layers,
reducing direct coupling between reports and pandas DataFrames.

## Validation before tagging

Run:

```cmd
pytest
python run_all.py
```

Confirm:

- all tests pass;
- `output/latest.xlsx` is generated;
- `Decision Analysis` exists;
- Morning Brief includes decision, conviction, thesis and action;
- SQLite history is updated;
- logs and metrics are created.
