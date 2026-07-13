# Scoring Model

The executable scoring path is:

```text
config/features.yaml + config/model.yaml
                  ↓
          factors/engine.py
                  ↓
       scoring/investment.py
                  ↓
Investment / Opportunity / Conviction
                  ↓
Deal Breakers / Decision / Thesis
```

The four factor scores are Business, Valuation, Financial and Timing.
`Confidence Score` is the model-coverage confidence produced by the active
factor engine; it is not the obsolete pre-scoring confidence calculation.

## Scores are relative to the run's batch

Each metric is scored by cross-sectional percentile rank *within the watchlist
analyzed in that run* (`factors/engine.py::pct_rank`). The Investment Score and
factor scores are therefore **relative positions, not absolute quality levels**:
the same fundamentals produce a different score when the peer set changes.

Measured magnitude (read-only probe, identical fundamentals, varying peers):
up to ~11–15 points of swing on small watchlists (n≈4–10), and up to the full
0–100 range in the theoretical extreme where every peer is strictly better or
worse. A single metric with ≤1 non-null value across the batch falls back to a
neutral 50.

Practical implications:

- Compare scores **within the same run**, not across runs with different
  watchlist membership.
- Keeping the watchlist stable across runs keeps scores comparable over time.
- Outcome calibration that pools scores across decision dates inherits this
  caveat — see `docs/OUTCOME_ANALYTICS.md`.

Configuration ownership:

- `config/features.yaml`: feature registry and feature-level weights;
- `config/model.yaml`: `factor_weights` — the factor-level weight vector;
- `config/deal_breakers.json`: governed risk-penalty rules and exemptions.

Changes to these files are financially material and require explicit tests and
documentation.
