# ADR-013 — Separate data evidence, confidence and risk uncertainty

**Status:** Accepted  
**Date:** 2026-07-17

## Context

Atlas previously used `Model Confidence`, `Confidence Score` and
`Score Coverage` as aliases for an unweighted mean of factor-level coverage.
`required: true` in the Feature Store had no executable effect. Missing inputs
to Deal Breaker rules were also indistinguishable from evidence that the rule
was safe, producing zero penalty in both cases.

## Decision

The scoring contract now exposes four independent dimensions:

- `Data Coverage`: percentage of the Investment Score's effective feature
  contribution backed by a numeric value. Feature weights and factor weights
  are both respected.
- `Model Confidence`: analytical confidence in the score. It starts from Data
  Coverage, but is capped at 59 when any governed `required` feature is absent.
- `Source Quality`: provenance score governed by `config/data_quality.yaml`.
- `Data Freshness`: age bucket governed by `config/data_quality.yaml`, evaluated
  at run time or at the point-in-time cutoff in historical replay.

`Confidence Score` remains an alias for Model Confidence and `Score Coverage`
remains an alias for Data Coverage solely for interface compatibility.

Every missing required feature is emitted in `Missing Required Features` and
the canonical ranking blocks it. Ranking also applies independent minimums for
Data Coverage, Source Quality and Data Freshness.

Deal Breakers now distinguish:

- `Observed Risk Penalty`: breached rules supported by evidence;
- `Risk Uncertainty Penalty`: missing evidence, 3 points per unassessable rule,
  capped at 10 by `config/deal_breakers.json`;
- `Risk Penalty`: the sum used by downstream decisions.

Missing evidence is listed in `Risk Evidence Missing` and never mislabeled as
an observed Deal Breaker. Sector exemptions continue to apply before a field is
classified as missing.

## Consequences

- A missing critical feature can no longer pass the candidate gate.
- Missing risk data is no longer economically equivalent to a safe observation.
- Scores and reports carry enough evidence metadata to explain why confidence
  is low.
- The broad-market rerun changed the candidate count from 1,042 to 794; this is
  an expected governed baseline change, not a provider failure.
- Historical inputs retain explicit source and cutoff-relative freshness. No
  current timestamp is injected into a past decision.

## Rollback

Revert this ADR and the corresponding config/code change. Existing database
columns are additive and may remain unused; no destructive schema migration is
required. Restoring old aliases alone is not sufficient because it would again
make missing risk evidence appear safe.
