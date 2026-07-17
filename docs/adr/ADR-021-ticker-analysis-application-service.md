# ADR-021 — Ticker analysis application service

**Status:** Accepted
**Date:** 2026-07-17

## Context

After ADR-020, `run_all.py` still implemented the complete `--ticker` flow:
market collection, official-reference scoring, score-history filtering,
portfolio-thesis lookup and one-pager publication. The pipeline exposed this
domain workflow through `RuntimeServices`, mixing operational functions with a
bounded analysis use case.

## Decision

1. `application/ticker.py` owns `TickerAnalysisApplicationService`.
2. The service composes minimal typed collection, scoring and history ports and
   receives config/output paths, logger and console output explicitly.
3. Single-symbol scoring continues to use the latest governed broad-market
   reference; the symbol is never scored against itself intentionally.
4. The service owns contribution calculation, symbol-history filtering,
   optional portfolio-thesis lookup and one-pager rendering/publication.
5. `TickerServices` becomes a separate orchestration facade. `TickerStage`
   loads settings through `RuntimeServices` and delegates analysis exclusively
   to `TickerServices`.
6. `run_all.run_ticker_mode()` remains a thin compatibility wrapper. During a
   pipeline run, the ticker service reuses the same concrete collection,
   scoring and history service instances created by the composition root.

## Consequences

- Runtime services contain only operational concerns.
- Ticker analysis is independently testable without network access.
- The official reference, optional portfolio thesis and existing HTML output
  behavior remain unchanged.
- Public CLI and helper signatures remain compatible.
- No score, decision, feature, reference or one-pager-content rule changes.

## Migration and rollback

No CLI, configuration or artifact migration is required. Rollback can move the
use-case implementation back to `run_all.py` and reattach it to
`RuntimeServices`; generated one-pagers require no conversion.
