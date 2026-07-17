# ADR-016 — Narrow typed pipeline service facades

**Status:** Accepted
**Date:** 2026-07-17

## Context

ADR-015 moved execution order out of `run_all.main()`, but the first migration
passed the entire imported `run_all` module as `PipelineContext.services`.
Stages therefore had an implicit service-locator dependency on every helper,
constant and imported object in that module. Artifact inputs and outputs were
typed, but operational dependencies were not restricted by responsibility.

## Decision

1. `PipelineServices` is an explicit immutable container, not a protocol that
   describes a module namespace.
2. It groups six typed facades:
   - `RuntimeServices`: paths, health, settings, console, metrics and ticker;
   - `CollectionServices`: watchlist loading/merge and provider collection;
   - `ScoringServices`: official reference, scoring, coverage, universe and
     ranking;
   - `HistoryServices`: model/history context, portfolio snapshot enrichment
     and outcome persistence;
   - `IntelligenceServices`: portfolio/watchlist intelligence and Atlas HTML;
   - `ReportingServices`: Excel, Morning Brief, priority, validation and
     Dashboard publication.
3. Public facade methods carry explicit input and return types. Provider-like
   functions with keyword-only parameters remain encapsulated behind those
   methods rather than being called dynamically by a stage.
4. `run_all.build_pipeline_services()` is the sole composition boundary. It
   binds the existing public helpers and governed paths to the facades.
5. Existing helpers remain public during this increment so tests and external
   callers are not broken. The pipeline itself never receives or inspects the
   `run_all` module.

## Consequences

- A stage's operational dependencies are visible from the facade it uses.
- Each stage's declared facade usage makes cross-responsibility calls visible
  in review and removes accidental reliance on unrelated module globals.
- Tests can substitute one responsibility without reproducing the entire
  `run_all` namespace.
- Existing calculation and output behavior is preserved because the adapters
  delegate to the same functions.
- Some callbacks inside the concrete facades remain implementation details;
  callers use typed public methods only.
- Collection and scoring callbacks are now bound directly to the concrete
  application services described in ADR-017.
- History and Outcome callbacks are bound to the concrete service described in
  ADR-018.
- Portfolio, watchlist and Atlas Report callbacks are bound to the concrete
  service described in ADR-019.

## Migration and rollback

No CLI, configuration, scoring or persisted-data migration is required.
Rollback replaces the facade container with the prior module-shaped service
object. Generated artifacts remain compatible in either direction.
