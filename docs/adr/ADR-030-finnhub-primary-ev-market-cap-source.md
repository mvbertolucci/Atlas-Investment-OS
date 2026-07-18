# ADR-030 — Finnhub as the primary live market-cap/EV secondary source

**Status:** Accepted
**Date:** 2026-07-18

## Context

ADR-025's FMP broad prefetch covered only 67/2,429 eligible symbols for
market cap and 6 for enterprise value before its 250-call daily quota ran
out (`docs/FMP_DATA.md`). This ADR was prompted by a direct question about
whether a genuinely better/easier free data source existed before building
more composition logic on top of the existing Massive+FMP+SEC stack.

A researched comparison against real official documentation (not aggregator
blog claims) of Alpha Vantage (25 calls/day), EODHD (20/day), Marketstack
(100/month), Twelve Data (~800/day) and Tiingo (fundamentals excluded from
the free tier entirely, confirmed via their own docs) found none of them
better than what Atlas already had. Finnhub was the one plausible unknown:
60 calls/minute with no documented daily cap, verified live rather than
assumed.

## Decision

1. Live-probe Finnhub's free tier before writing any integration code:
   `/stock/profile2` and `/stock/metric?metric=all` for AAPL both returned
   200 with real, correctly scaled data -- no premium-plan rejection.
   `/stock/metric` alone already includes `marketCapitalization` and
   `enterpriseValue` as vendor-computed absolute values (in millions), so no
   debt/cash composition is needed for those two fields, unlike Massive or
   FMP.
2. Add `providers/finnhub.py` (`FinnhubMarketDataProvider`, one call per
   symbol, `supported_fields = {"market_cap", "enterprise_value"}` only --
   it does not expose raw debt/cash, so it cannot feed Atlas's own Altman Z
   / ROIC / Interest Coverage formulas) and `providers/finnhub_cache.py` (a
   2-day TTL per-symbol cache, mirroring the existing per-provider cache
   shape).
3. Add `providers/finnhub_prefetch` (CLI), cache-first and resumable like
   the other broad prefetch CLIs, batched by default at 55/invocation to
   match the per-minute pacing.
4. In `application/collection.py`'s live per-symbol secondary chain, place
   `finnhub_fetcher` first in `secondary_fetchers` (ahead of Massive and
   FMP). Because `reconcile_critical_fields` statically assigns each
   critical field to the first fetcher in priority order that declares
   support for it (`providers/yahoo.py::fetch_watchlist`), this makes
   Finnhub the confirming/fallback source for `market_cap`/`enterprise_value`
   -- Massive's own SEC-composed values for those two fields are no longer
   used in this reconciliation, though Massive still runs unconditionally
   and still claims `short_float` (unaffected, ~97% broad coverage). FMP's
   role is unchanged: still Massive's internal Float fallback, and its
   `market_cap`/`enterprise_value` claim was already excluded from
   reconciliation before this change (Massive claimed those fields first,
   pre-ADR-030).

## Consequences

- Live-verified against the real chain (AAPL, 2026-07-18):
  `field_evidence.market_cap.confirmed_by == "Finnhub"`,
  `secondary_raw_snapshots` includes `Finnhub` alongside `SEC EDGAR Company
  Facts` and `Massive` -- all three ran; Yahoo's own value won because it was
  already present (the reconciliation chain is a fallback/confirmation net,
  not an override).
- Broad coverage: a bounded 20-symbol live prefetch run against the real
  eligible universe completed with 0 errors. A full 2,429-symbol cold run is
  estimated at ~45 minutes (55-60/minute vs FMP's 250/day quota wall or
  Massive Ticker Details' ~8-hour scan) and has not been run to completion
  yet -- tracked as a follow-up in `docs/BACKLOG.md`.
- No governed scoring weight, threshold or formula changes. Massive's SEC-
  composed EV mechanism (ADR-026) and the Grouped Daily price mechanism
  (ADR-029) are unchanged and still available -- this ADR does not retire
  either; it changes which source is tried first for two specific fields in
  the live reconciliation chain.
- Finnhub cannot replace SEC EDGAR for Atlas's own formulas (no raw
  debt/cash), so the SEC dependency for Altman Z, ROIC, Interest Coverage
  and Piotroski F-Score is unaffected.

## Rollback

Remove `finnhub_fetcher` from the `secondary_fetchers` tuple in
`application/collection.py` (single-line revert) or set
`finnhub_secondary_enabled: false`. Massive returns to being the first
claimant of `market_cap`/`enterprise_value`, exactly as before this ADR. The
ignored `data/provider_cache/finnhub.json` cache can be deleted without
affecting any other provider.
