# ADR-019 — Intelligence application service

**Status:** Accepted
**Date:** 2026-07-17

## Context

After ADR-018, historical persistence had an application owner, but
`run_all.py` still implemented portfolio intelligence and watchlist tracking,
while Atlas Report construction was injected as unrelated rendering callbacks.
These operations consume the same scored/historical context and collectively
produce the decision intelligence presented before the final export stage.

## Decision

1. `application/intelligence.py` owns
   `IntelligenceApplicationService`.
2. The service receives root/config/output paths, the history database,
   portfolio/watchlist report paths and logger explicitly.
3. It owns portfolio intelligence without changing the advisory rebalance or
   blocked-sell semantics.
4. It owns watchlist trigger evaluation, aging, trigger-history persistence and
   Watchlist Report publication. Watchlist processing remains independent of
   portfolio sell-engine availability.
5. It owns `STATUS.md` diagnostics, Atlas `ReportContext` construction and
   combined HTML rendering/writing.
6. `run_all.build_pipeline_services()` binds the concrete methods directly to
   `IntelligenceServices`. The pipeline no longer obtains report diagnostics
   from `RuntimeServices`.
7. Existing `run_all` portfolio/watchlist functions and `_read_status_md`
   remain thin compatibility wrappers using current module paths.

## Consequences

- Portfolio, watchlist and Atlas Report orchestration have one application
  boundary.
- The Atlas Report render/write operation cannot be partially wired by the
  composition root; it is exposed as one typed service method.
- Missing portfolio/watchlist inputs remain explicit, conservative no-ops.
- Existing public helper signatures and output files remain compatible.
- No rebalance, trigger, aging, scoring, decision or report-content semantics
  change.

## Migration and rollback

No caller or persisted-data migration is required. Existing report JSON, HTML
and watchlist-trigger history remain compatible. Rollback can restore the thin
service implementations to `run_all.py` without transforming artifacts.
