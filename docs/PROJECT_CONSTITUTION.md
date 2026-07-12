# Atlas Project Constitution

## Article 1 — Purpose

Atlas exists to transform financial data into reproducible, auditable and explainable investment decisions and portfolio insights.

## Article 2 — Safety and scope

Atlas is decision support. It must not represent advisory rebalance suggestions as automatic trade instructions, guarantee outcomes or conceal uncertainty in source data.

## Article 3 — Reproducibility

The same inputs and governed configuration should produce the same deterministic calculations. External-data timestamps and missing fields must remain visible.

## Article 4 — Explainability

Scores, penalties, Deal Breakers, decisions and portfolio warnings must be traceable to named inputs and rules.

## Article 5 — Configuration governance

Financially material weights, thresholds and definitions live in explicit configuration files. They are never changed incidentally during refactoring.

## Article 6 — Regression discipline

Every behavioral change requires tests. Existing contracts remain valid unless a documented migration is deliberately approved.

## Article 7 — Atomic evolution

Each PR has one primary objective, a clear validation record and an understandable rollback path.

## Article 8 — Living documentation

Architecture, feature status and handoff context are updated in the same PR that changes them. Executable code and tests win when stale documents conflict, and the documents must then be corrected.

## Article 9 — Data and repository hygiene

Secrets, runtime output, logs and local databases are not committed. Tests must avoid dependence on live network services.

## Article 10 — Human authority

High-impact actions—changes to scoring policy, publication, releases, merges and investment use—remain subject to human review.
