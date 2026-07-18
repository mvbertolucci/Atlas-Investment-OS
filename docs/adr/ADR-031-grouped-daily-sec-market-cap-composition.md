# ADR-031 — Compose broad market cap from Grouped Daily price x SEC shares

**Status:** Accepted
**Date:** 2026-07-18

## Context

ADR-029 built the Grouped Daily price mechanism but deliberately left the
other half of the original BACKLOG item undone: composing
`market_cap = price x SEC shares_outstanding` into a broad snapshot. ADR-030
(Finnhub) separately closed the practical need for broad `market_cap`/
`enterprise_value` in the live per-symbol reconciliation chain, so this ADR
is not urgent in the way it was before -- but it still delivers real value:
a broad market-cap path that depends on no external vendor beyond Massive
and SEC EDGAR, both already integrated and both free without a daily-call
ceiling comparable to FMP's.

## Decision

1. `providers/market_cap_composition.py::compose_market_cap` -- a pure
   function, no network: `market_cap = Grouped Daily close x SEC
   shares_outstanding`, composed only when both are present and their dates
   fall within an alignment window. Never invents either component.
2. **Alignment window is 100 days, not 45.** The existing 45-day convention
   (`sec_public_float_alignment_days`, used for EV's debt/cash and
   short_float's float/short-interest pairing) exists because those
   components can move materially within a quarter and the SEC monetary
   public-float-to-shares conversion is price-sensitive. `shares_outstanding`
   is a share *count* that only changes via deliberate buybacks/issuance and
   is reported quarterly (10-Q); live-verified against AAPL: SEC
   `shares_outstanding` observed 2026-04-17, Grouped Daily trade date
   2026-07-16 -- 90 days apart, itself close to the 45-day threshold's
   limit. A 100-day window (one fiscal quarter plus 10-Q filing lag) is the
   correct judgment for this specific pairing, not a copy of the EV
   convention. Governed by `market_cap_composition_shares_alignment_days`.
3. `providers/sec_shares_cache.py::SecSharesCache` -- a new, separate
   persistent per-symbol cache (30-day default TTL, since a new 10-Q only
   changes the value quarterly), external to `SecCompanyFactsProvider`
   itself so the live per-symbol contract in `providers/sec_companyfacts.py`
   is untouched by this addition.
4. `providers/market_cap_composition_prefetch` (CLI): reads the eligible
   universe, the latest cached Grouped Daily trade date (or `--date`),
   fetches/caches SEC shares_outstanding per symbol at the same paced rate
   already used by `sec_public_float_audit.py`
   (`sec_public_float_rate_limit_per_second`), composes, and writes both a
   coverage report and the full composed snapshot.

## Consequences

- Live-verified against the real eligible universe (2026-07-18, 8 symbols,
  trade date 2026-07-16): 7/8 composed, 0 fetch errors, 1 correctly excluded
  as `shares_stale` (SEC observation 107 days old). AAPL composed to
  $4.8947T -- within ~1% of the two independent compositions already
  measured for the same company (Massive Ticker Details ~$4.90T, Finnhub
  ~$4.86T), a real cross-validation signal across three independently
  implemented paths.
- No governed scoring weight, threshold or formula changes; this composed
  snapshot is not wired into any production decision path yet (mirrors
  ADR-029's own scope boundary).
- A full 2,429-symbol broad run has not been executed; SEC EDGAR's fair-use
  pacing (2/second) puts a cold run at roughly 20 minutes, tracked as a
  follow-up in `docs/BACKLOG.md` alongside the Finnhub broad run.

## Rollback

Delete the ignored `data/provider_cache/sec_shares.json` cache and stop
invoking the prefetch CLI. `compose_market_cap` and `SecSharesCache` are
additive; nothing else imports them.
