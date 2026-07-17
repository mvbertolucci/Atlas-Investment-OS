# ADR-020 — Reporting application service

**Status:** Accepted
**Date:** 2026-07-17

## Context

After ADR-019, the pipeline consumed concrete application services for every
stage except final publication. `run_all.py` still implemented Excel, Morning
Brief, priority, performance-validation and dashboard generation and exposed
those functions to `ReportingServices`. This left the composition root with
report workflow rules, governed paths and cross-report aggregation logic.

## Decision

1. `application/reporting.py` owns `ReportingApplicationService`.
2. The service receives report destinations, the history database, the broad
   research-ranking input and logger explicitly.
3. It owns final Excel and Morning Brief generation, buy/sell priority
   publication, performance validation and read-only dashboard aggregation.
4. Feature flags and existing report/domain builders remain authoritative;
   this change does not redefine report content or scoring semantics.
5. `run_all.build_pipeline_services()` creates one concrete service and binds
   its methods directly to `ReportingServices`.
6. Historical `run_all` functions remain thin compatibility wrappers built
   from the current module paths. Morning Brief ports remain injectable so
   established integration seams continue to work.

## Consequences

- `run_all.py` is limited further toward CLI and composition responsibilities.
- Final publications share one explicit application boundary and one governed
  set of destinations during a pipeline run.
- Reporting can be tested independently of the full pipeline.
- Public helper signatures, flags, report formats and paths remain compatible.
- No score, decision, ranking, rebalance or Outcome Analytics rule changes.

## Migration and rollback

No caller or artifact migration is required. Rollback can move the thin method
implementations back into `run_all.py`; existing JSON, Markdown and Excel files
need no conversion.
