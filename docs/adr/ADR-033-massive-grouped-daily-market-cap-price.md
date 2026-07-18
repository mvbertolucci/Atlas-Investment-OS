# ADR-033 — Massive Grouped Daily as the broad market-cap price source

**Status:** Accepted
**Date:** 2026-07-18

## Context

The broad Ticker Details scan (`providers/massive_prefetch.py`) is the only
existing path to Massive-confirmed market cap across the eligible universe,
but Stocks Basic permits five calls per minute: a cold 2,429-symbol pass takes
about 8.1 hours (ADR-027), and no complete broad run had been executed —
`docs/BACKLOG.md` carried an open item to replace it with a composed path
using Massive Grouped Daily prices and aligned SEC shares outstanding
(`shares_outstanding` is already extracted per symbol by
`providers/sec_companyfacts.py::record_from_company_facts`, ADR-014/026).

Grouped Daily was not yet used anywhere in Atlas and was not in the documented
Basic-plan endpoint list (`docs/MASSIVE_DATA.md`), so before writing any
composition logic this decision required a bounded live check of entitlement
and shape, the same discipline already applied to every other Massive
endpoint in this codebase.

## Decision

1. Live-probe `GET /v2/aggs/grouped/locale/us/market/stocks/{date}` with the
   configured personal key before building anything on top of it. Confirmed
   Basic-plan access: one call for `2026-07-16` returned 12,452 tickers with
   `T` (symbol) and `c` (close), plus `o`/`h`/`l`/`v`.
2. Add `MassiveMarketDataProvider.fetch_grouped_daily(trade_date)` — one typed,
   rate-paced request per date, normalized into `{SYMBOL: {trade_date, close,
   open, high, low, volume}}`, dropping rows without a symbol or a close.
3. Add `MassiveGroupedDailyCache`, keyed by trade date rather than by symbol
   or page cursor: a past date's EOD bars are immutable, so a cache hit never
   re-requests the network (unlike Ticker Details/Float, which describe
   *current* state and expire).
4. Add `providers/massive_grouped_daily_prefetch` (CLI), mirroring the
   established float-prefetch shape: fetch (or reuse the cached) snapshot for
   one trade date, report coverage against `US_MARKET_ELIGIBLE`, write an
   ignored coverage report.
5. This ADR delivers the price-fetch mechanism only. Composing
   `market_cap = Grouped Daily close × SEC shares_outstanding` (with the same
   45-day alignment discipline already used for EV and short float) is the
   explicit next step, tracked separately in `docs/BACKLOG.md` — kept as its
   own atomic change rather than folded in here, consistent with how Massive
   market cap/EV/float were each their own ADR.

## Consequences

- Live verification (2026-07-16 trade date, real eligible universe): one
  request returned 12,452 market records and matched 2,423/2,429 eligible
  symbols directly (99.75%) — close to the 97.3% Massive Float already
  achieves via market-wide pagination, from a single call instead of a
  multi-page scan. The 6 unmatched symbols are not yet classified (no SEC
  audit run against them, unlike the residual Float gaps in ADR-028) and
  should not be assumed unavailable, delisted or newly listed without
  checking.
- The existing per-symbol Ticker Details path is unchanged and remains
  available for targeted single-symbol confirmation (per the original
  BACKLOG wording); nothing here removes or reduces its 8-hour broad scan
  capability, it simply stops being the only broad market-cap price option.
- No governed scoring weight, threshold or historical record changes; this is
  additive provider infrastructure, not yet wired into any production
  decision path.

## Rollback

Remove the ignored `data/provider_cache/massive_grouped_daily.json` cache and
stop invoking the prefetch CLI. `fetch_grouped_daily` and
`MassiveGroupedDailyCache` are additive; no other code path calls them.
