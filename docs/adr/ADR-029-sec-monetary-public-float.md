# ADR-029 — Keep SEC monetary public float separate from share count

**Status:** Accepted
**Date:** 2026-07-17

## Context

Sixty-four eligible symbols remained without dated Massive or FMP free-float
shares. SEC Company Facts can expose `dei:EntityPublicFloat`, but its definition
is aggregate USD market value held by non-affiliates, not number of shares. The
fact does not disclose the exact last-sale or bid/ask price basis used by the
filer.

## Decision

1. Extract the latest non-negative USD fact from annual 10-K, 20-F or 40-F
   filings as the distinct field `entity_public_float_value`.
2. Preserve its observation and availability dates and immutable raw snapshot
   hash.
3. Audit it against the governed 45-day short-interest alignment window.
4. Never relabel the monetary value as `free_float`, divide it by a current or
   assumed price, or use outstanding shares as a substitute.
5. Keep structural groups as review aids only; they do not automatically mark
   an issuer as sector-not-applicable.

## Consequences

- The real 64-symbol audit found 28 positive but stale monetary values, 30
  absent facts, 3 zeros and 3 provider/mapping failures.
- The newest positive observation was 290 days old, so zero observations were
  eligible even before the missing exact price basis was considered.
- Combined free-float availability remains 2,365/2,429 (97.37%), with 64
  explicit gaps and no artificial improvement in risk coverage.

## Rollback

The audit command and distinct SEC field can be removed without changing
scores. Converting the monetary fact into shares requires a new versioned
decision with evidence that the filer-specific price and share class are exact.
