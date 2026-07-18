# ADR-027 — Resumable Massive Basic Ticker Details cache

**Status:** Accepted
**Date:** 2026-07-17

## Context

Ticker Details is available in Massive Stocks Basic, but the plan permits only
five API calls per minute. Collecting 2,429 symbols without persistence would
take hours and any interruption would waste completed calls.

## Decision

1. Atomically cache each Ticker Details response by normalized symbol for seven
   days; cache definitive 404 responses as unavailable.
2. Treat the cache as the resumable checkpoint and skip every fresh record.
3. Pace all Massive requests with a five-call rolling minute window and broad
   prefetch at 4.5 calls/minute for safety margin.
4. Default the CLI to five new symbols; support `--all` for an interruptible
   long run.
5. Publish requested, cached, available, missing, remaining, errors and
   coverage percentage against the official eligible universe.
6. Stop a batch on authentication or exhausted rate limit instead of repeating
   failures.

## Consequences

- The first fast live attempt retained five successes before HTTP 429. A
  resumed five-symbol batch at the governed rate completed without errors,
  proving checkpoint continuity.
- A cold full scan takes approximately 8.1 hours and can be safely resumed.
- Initial 10/2,429 coverage is only progress; final broad coverage remains an
  open measurement.
- Cache and coverage outputs remain ignored runtime artifacts.

## Rollback

Disable the Massive provider or remove its ignored cache. Removing the cache
causes re-collection but does not change governed scoring configuration.
