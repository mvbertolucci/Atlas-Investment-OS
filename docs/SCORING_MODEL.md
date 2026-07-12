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

- `config/features.yaml`: feature registry and feature-level definitions;
- `config/model.yaml`: factor composition;
- `config/weights.json`: integrated investment-model weights;
- `config/deal_breakers.json`: governed exclusion and risk rules.

Changes to these files are financially material and require explicit tests and
documentation.
