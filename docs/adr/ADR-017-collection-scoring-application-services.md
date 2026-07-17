# ADR-017 — Collection and scoring application services

**Status:** Accepted
**Date:** 2026-07-17

## Context

ADR-016 replaced module-namespace injection with narrow typed facades, but the
callbacks bound to `CollectionServices` and `ScoringServices` still pointed to
large implementations defined in `run_all.py`. The composition root therefore
remained responsible for provider policy, enrichment, official-reference
validation and governed scoring paths.

## Decision

1. `application/collection.py` owns the concrete
   `CollectionApplicationService`, including watchlist loading, provenance
   merge, provider policy, immutable-snapshot-aware collection and analytical
   enrichment.
2. `application/scoring.py` owns `ScoringApplicationService`, including the
   official broad-market reference, governed normalization/scoring, feature
   coverage audit, universe evaluation and analytical ranking.
3. Both services receive root/config/output paths and the logger explicitly.
   Governed configuration filenames and all scoring semantics remain
   unchanged.
4. `run_all.build_pipeline_services()` binds application-service methods
   directly to the orchestration facades. Pipeline execution does not call the
   compatibility wrappers.
5. The historical public functions in `run_all.py` remain thin wrappers. They
   construct a service from the current module constants for every call,
   preserving existing callers and tests that override output paths.
6. Origin constants remain re-exported from `run_all.py` for compatibility,
   while their owner is now `application.collection`.

## Consequences

- Provider and scoring implementation details no longer live in the CLI
  composition module.
- Collection and scoring can be tested directly without constructing the full
  pipeline.
- The pipeline receives concrete bound methods rather than wrappers or a
  module service locator.
- Compatibility wrappers add a small object-construction cost only for direct
  legacy calls; the normal pipeline constructs one service instance per run.
- No score, percentile, eligibility, Deal Breaker or output contract changes.

## Migration and rollback

No caller migration is required. New code should import the application
services; existing code may continue importing the public `run_all` functions.
Rollback can restore the implementations inside `run_all.py` without a data or
configuration migration.
