# ADR-025 — Persistent cache and quota boundary for free FMP data

**Status:** Accepted
**Date:** 2026-07-17

## Context

FMP Basic documents a 250-call daily allowance. Per-symbol collection cannot
safely confirm a 2,429-company universe, must not consume the allowance needed
for an interactive ticker run, and must not repeatedly request data the account
is not entitled to receive.

## Decision

1. Persist FMP responses by symbol and category with atomic writes and TTLs.
2. Persist a separate UTC-day call ledger and reserve 25 calls for interactive
   collection.
3. Prefetch market cap in batches, float in pages and enterprise components
   resumably only for symbols with market-cap evidence.
4. Cache empty results after a complete scan or HTTP 402, while preserving the
   semantic distinction between cached and available.
5. Make broad-prefetched symbols cache-only for the remainder of the process.
6. Report requested, cached, available, missing, error and quota counts.

## Consequences

- Repeated runs reuse evidence and stop before the daily reserve.
- Unsupported data stays unavailable and cannot become false confirmation.
- The 2026-07-17 live scan found market-cap and float evidence for 67 of 2,429
  eligible symbols. FMP Basic is therefore useful but not a broad independent
  confirmation source.
- Completing second-source coverage requires another legally usable provider
  or an explicit product decision to accept the limitation.

## Rollback

Disable `fmp_secondary_enabled`. Local cache files may remain ignored; deleting
them only removes reusable evidence and quota history, not governed scores.
