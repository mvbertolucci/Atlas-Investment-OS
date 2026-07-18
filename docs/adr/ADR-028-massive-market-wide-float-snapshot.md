# ADR-028 — Market-wide Massive Float snapshot

**Status:** Accepted
**Date:** 2026-07-17

## Context

Free float is a dated denominator required for `short_float`. Calling Massive
Float once per eligible ticker would duplicate work and consume scarce Basic
rate-limit capacity, even though the endpoint can return the market in pages.
Outstanding shares are not a valid substitute for free float.

## Decision

1. Request `GET /stocks/vX/float` without a ticker and follow its pagination.
2. Atomically checkpoint every successful page in one seven-day market
   snapshot, retaining completion state and the next safe request.
3. Accept cursors only from `api.massive.com` stock paths and remove any API key
   before persistence.
4. Resolve Atlas hyphenated share classes against Massive dotted symbols.
5. Treat absence from a complete fresh snapshot as authoritative for that
   source, suppressing per-ticker Float calls.
6. Preserve dated FMP Float as fallback; never infer free float from
   outstanding shares.
7. Publish an ignored coverage report against `US_MARKET_ELIGIBLE`.

## Consequences

- The first complete live snapshot required seven calls and returned 6,662
  market records without errors.
- Massive directly matched 2,364/2,429 eligible symbols (97.32%). Dated FMP
  evidence adds `ET`, producing 2,365/2,429 combined availability (97.37%).
- The remaining 64 symbols stay explicitly unavailable until a definition- and
  date-aligned source is proven.
- Normal watchlist and ticker runs reuse the snapshot and avoid N+1 Float
  traffic.

## Rollback

Disable or remove the ignored snapshot. The provider then returns to bounded
per-ticker Float requests until a fresh complete market snapshot is built.
