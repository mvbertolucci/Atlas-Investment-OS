# Advisory Model Portfolio

## Purpose

PR-031 converts the complete broad-universe checkpoint into an auditable
research portfolio. It is a model output for validation, not a trade order,
personal recommendation or performance promise.

The command is explicit and remains separate from `run_all.py`:

```powershell
.\.venv\Scripts\python.exe -m portfolio.model_portfolio
```

It writes three ignored runtime artifacts:

- `output/research_universe_report.json` — eligibility of all observations;
- `output/research_ranking_report.json` — broad market and sector ranking;
- `output/model_portfolio_report.json` — constrained advisory selection.

## Method

The command loads the completed collection checkpoint, applies the existing
Atlas normalization and governed scoring pipeline, evaluates the existing
universe policy and applies the existing ranking safeguards. It introduces no
new alpha score and does not modify factor weights, Deal Breakers or candidate
thresholds.

Selection follows `candidate_rank` and greedily accepts the best remaining
company whose addition does not breach the sector cap. The first policy is
deliberately simple:

| Constraint | Value |
|---|---:|
| Positions | 20 |
| Weighting | Equal |
| Maximum position | 5% |
| Maximum sector | 20% |
| Structural cash | 0% |
| Maximum initial turnover | 100% |

These values live in `config/model_portfolio.yaml` and are pinned by governance
tests. They are assumptions to validate, not calibrated optimal values.

## Failure behavior

Construction stops explicitly when:

- collection is incomplete or retains provider failures;
- the policy constraints are internally incompatible;
- too few safeguarded candidates remain to satisfy position and sector limits;
- output types do not match the documented contracts.

The output records source dates, eligible/candidate counts, ranks, existing
scores, target weights, sector weights, reference prices and any higher-ranked
candidate skipped by diversification constraints.

## Validation boundary

The portfolio uses a current constituent snapshot and current provider data.
It therefore cannot establish historical performance and must not be treated
as backtest evidence. PR-032 defines point-in-time data rules before PR-033
implements walk-forward testing. A later prospective shadow portfolio will
freeze recommendations before observing outcomes.
