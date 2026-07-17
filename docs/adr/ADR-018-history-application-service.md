# ADR-018 — History application service

**Status:** Accepted
**Date:** 2026-07-17

## Context

After ADR-017, collection and scoring were concrete application services, but
historical execution still combined imported domain functions and
`run_all.py` implementations. Model-version loading, previous-run selection,
portfolio quantity support, SQLite snapshots, outcome capture/evaluation and
the aggregate Outcome report had no single application-level owner.

## Decision

1. `application/history.py` owns `HistoryApplicationService`.
2. The service receives root/config paths, the history database, the Outcome
   report path and logger explicitly.
3. It exposes typed operations for model configuration, score history,
   previous-run context, sell-rule policy, portfolio loading, score snapshots,
   outcome capture, due-outcome evaluation and Outcome Analytics publication.
4. `run_all.build_pipeline_services()` binds these methods directly to
   `HistoryServices`; normal pipeline execution does not call `run_all`
   wrappers.
5. Existing public `run_all` functions for saving history and processing
   outcomes remain thin wrappers. They construct the service from the current
   module paths so temporary-path overrides and external callers remain
   compatible.
6. Single-ticker report preparation may continue using read-only historical
   domain functions directly until its reporting service is extracted; it does
   not own persistence.

## Consequences

- Historical persistence and Outcome Analytics have one application boundary.
- Previous-run selection and model-version comparison are available through
  the same service that writes snapshots.
- SQLite paths and Outcome output paths are explicit constructor inputs.
- The pipeline uses a concrete bound service while legacy direct calls retain
  their prior signatures.
- No database schema, outcome horizon, return calculation, score or report
  contract changes.

## Migration and rollback

No data or caller migration is required. Existing SQLite databases and Outcome
JSON files remain compatible. Rollback may restore wrapper implementations to
`run_all.py` without transforming persisted data.
