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

Configuration ownership:

- `config/features.yaml`: feature registry and feature-level weights;
- `config/model.yaml`: `factor_weights` — the factor-level weight vector;
- `config/deal_breakers.json`: governed risk-penalty rules and exemptions.

Changes to these files are financially material and require explicit tests and
documentation.
