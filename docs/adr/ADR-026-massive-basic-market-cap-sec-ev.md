# ADR-026 — Massive Basic market cap and SEC-composed enterprise value

**Status:** Accepted
**Date:** 2026-07-17

## Context

The Massive Financial Ratios endpoint rejects the configured Basic account,
while Basic Ticker Details includes market capitalization and outstanding
shares. FMP Basic exposes only a small entitlement subset in the eligible
universe. SEC Company Facts already supplies dated debt and cash components.

## Decision

1. Read `market_cap` from Massive `/v3/reference/tickers/{ticker}` and stop
   requesting paid Financial Ratios.
2. Derive `enterprise_value = Massive market_cap + SEC total_debt - SEC
   total_cash` only when both SEC components exist and their periods are within
   45 days.
3. Prefer Massive native Float for `short_float`; invoke FMP Float only when the
   native value is absent or misaligned, and accept it only if dates align.
4. Cache SEC Company Facts records in memory per run so composition does not
   repeat EDGAR downloads.
5. Keep automatic broad FMP prefetch disabled. Its explicit resumable CLI
   remains available.
6. Use the persistent, rate-bounded broad Massive collection defined by
   ADR-027 before making market-wide coverage claims.

## Consequences

- No paid Massive ratios subscription is required for current market cap or
  composed EV.
- Bounded live validation produced market cap for AAPL, AVAV and BNTX; EV for
  AAPL and AVAV; and dated short float for all three. BNTX EV correctly remained
  unavailable because comparable SEC components were not both available.
- Broad 2,429-symbol Massive coverage is not yet claimed. ADR-027 implements
  the required collector; its checkpoint must still be completed.

## Rollback

Disable `massive_secondary_enabled`. SEC and FMP remain independent providers;
no governed score weights, thresholds or historical records require migration.
