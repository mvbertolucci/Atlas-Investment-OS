# ADR-024 — Free composed market evidence

**Status:** Accepted
**Date:** 2026-07-17

## Context

ADR-026 supersedes FMP as the first-choice market-cap and EV source. This
decision remains active for the FMP fallback and its quota boundary.

Massive Basic permits Short Interest and Float but denies Financial Ratios.
Its AAPL Float observation was also too old to align with current Short
Interest under Atlas's 45-day rule. Buying a ratios expansion is unnecessary:
FMP Basic exposes current market cap, enterprise-value components and a more
recent float under a documented free request allowance.

## Decision

1. Use free FMP as the declared secondary for `market_cap`.
2. Derive current `enterprise_value` from FMP current market cap plus its latest
   reported debt minus cash, recording both valuation and component dates.
3. Derive `short_float` from Massive Short Interest and FMP Float only when
   their dates differ by at most 45 days.
4. Keep credentials isolated and snapshot each provider/composition without
   keys.
5. Skip the denied Massive Ratios call whenever FMP is active.
6. Do not run the per-symbol FMP adapter over the broad universe; use the
   persistent batch/cache/quota orchestration defined by ADR-025.

## Consequences

- AAPL live validation confirmed all three fields within the governed 5%
  tolerance without a paid subscription.
- The resulting `short_float` names both contributing providers; it is not
  misrepresented as a native FMP or Massive field.
- Ticker, watchlist and portfolio coverage is immediately useful.
- Broad-universe confirmation is quota- and entitlement-limited. The live
  Basic scan exposed market-cap/float records for only 67/2,429 eligible
  symbols; all other cases remain explicitly unavailable.

## Rollback

Disable `fmp_secondary_enabled`. Massive then returns to its native Float
endpoint and continues withholding misaligned periods.
