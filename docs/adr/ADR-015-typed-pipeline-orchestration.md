# ADR-015 — Typed pipeline orchestration

**Status:** Accepted
**Date:** 2026-07-17

## Context

The official `run_all.py` entry point accumulated the entire execution order,
intermediate local variables, mode branches, persistence, reporting and final
presentation in one function. Individual domain helpers were testable, but the
workflow itself had no explicit contract: an intermediate value could be
omitted, passed in the wrong order or changed without a stage boundary making
the dependency visible.

## Decision

1. `run_all.py` remains the stable executable entry point, but `main()` only
   parses the CLI request, creates `PipelineContext`, selects a pipeline and
   executes it.
2. `orchestration/pipeline.py` owns the workflow as explicit stages. Each stage
   declares `requires`, an `output_type` and a `run(context)` operation.
3. `PipelineContext` stores the request, execution metrics, injected services
   and typed output artifacts. Publishing the same artifact type twice or
   requiring one that has not been produced is an execution error.
4. `PipelineRunner` validates required artifacts before each stage and checks
   the concrete output type before publishing it.
5. Full and portfolio modes share the same ordered stages; governed screener
   outputs remain conditional inside scoring according to the requested mode.
   Single-ticker execution uses its own bounded stage and retains the official
   broad-market scoring reference through the existing ticker service.
6. Existing `run_all` helper functions and constants are injected as the
   service boundary during this migration. This preserves public interfaces,
   monkeypatch seams and all scoring/report semantics while moving ownership of
   execution order out of the entry point.

## Consequences

- Stage order, dependencies and outputs are inspectable and regression-tested.
- Missing intermediate state fails at the nearest boundary with the artifact
  type named in the error.
- New stages can be inserted without growing the CLI entry function.
- The initial module-shaped service boundary was replaced by the narrow typed
  facades recorded in ADR-016 without changing stage artifact contracts.
- This refactor changes orchestration only. It does not change governed
  features, weights, thresholds, scoring, eligibility or output formats.

## Migration and rollback

The CLI commands and generated artifact contracts are unchanged. Rollback is a
code revert to the prior monolithic `main()`; no persisted-data migration is
required.
