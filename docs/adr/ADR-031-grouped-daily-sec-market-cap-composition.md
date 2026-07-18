# ADR-031 — Compose broad market cap from Grouped Daily price x SEC shares

**Status:** Accepted
**Date:** 2026-07-18

## Context

ADR-033 built the Grouped Daily price mechanism but deliberately left the
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
  ADR-033's own scope boundary).
- A full 2,429-symbol broad run has not been executed; SEC EDGAR's fair-use
  pacing (2/second) puts a cold run at roughly 20 minutes, tracked as a
  follow-up in `docs/BACKLOG.md` alongside the Finnhub broad run.

## Rollback

Delete the ignored `data/provider_cache/sec_shares.json` cache and stop
invoking the prefetch CLI. `compose_market_cap` and `SecSharesCache` are
additive; nothing else imports them.

## Update (2026-07-18) — alignment window widened to 140 days, measured

The full 2,429-symbol broad run this ADR flagged as not yet executed
completed: 1,724 composed (70.98%). `shares_stale` (300 symbols) was not a
uniform bucket -- measuring the real age distribution against the 100-day
window found 142 symbols only 101-130 days old (consistent with SEC's own
worst-case quarterly cadence: a non-accelerated filer's 10-Q is due up to 45
days after quarter-end, ~91 days separate quarters, so two on-time
consecutive filings can be up to ~136 days apart) against 119 symbols 365+
days old (one over 6,000 days -- dead/shell-company territory, not a filing-
cadence question). Widened `market_cap_composition_shares_alignment_days` to
140 -- grounded in the measured SEC cadence, not the 365+ bucket, which stays
correctly excluded rather than papered over. The wider window only needed
recomposing already-cached data (`SecSharesCache` entries were still fresh),
no new SEC calls. `shares_unavailable` (399, including 128 explicit fetch
errors) is a separate gap this widening does not address -- would need a
second shares-outstanding source (Massive Ticker Details returns
`share_class_shares_outstanding`, unused today) as a tracked follow-up in
`docs/BACKLOG.md`.

## Update (2026-07-18) — malformed-entry fix (ADR-034) and Massive fallback

Two more rounds after the window widening, prompted by the user asking for
more coverage than 76.99% (window widening) and then again past 80.03%
(ADR-034's extraction fix): investigated instead of guessing each time.

ADR-034 fixed `backtesting/sec_edgar.py::extract_observations` aborting a
company's *entire* extraction over one malformed entry in an unrelated
field -- recovered 74 symbols, 76.99% -> 80.03%.

Investigating the remaining `shares_unavailable` gap found ABNB (Airbnb) --
no error, `shares_outstanding` genuinely `None`. Live-checked ABNB's raw SEC
company facts directly: its `dei` taxonomy is completely empty, no
`EntityCommonStockSharesOutstanding` or `CommonStockSharesOutstanding` tag
at all -- not a bug, a real SEC-side gap (plausibly its dual-class share
structure never rolls up into a flat cover-page fact the way single-class
filers' does). This confirmed the remaining gap is genuinely two separate
real limitations, not a hidden third bug: closed-end funds with no 10-K/10-Q
XBRL, and companies whose SEC tagging has no clean shares-outstanding fact.

Implemented the Massive Ticker Details fallback flagged above:
`_fetch_massive_shares` in `market_cap_composition_prefetch` tries Massive's
`share_class_shares_outstanding` (computed through Massive's own pipeline,
independent of raw SEC XBRL) only when SEC has none, bounded by its own
5-call/minute pacing and a separate per-run budget
(`market_cap_composition_massive_fallback_batch_size`, default 5;
unbounded under `--all`) so a normal run never accidentally burns Massive's
slow quota on a large batch. `compose_market_cap` gained a `shares_source`
parameter so composed records and their evidence detail say which source
actually supplied the count. Live-verified: ABNB itself composed correctly
once Massive supplied `share_class_shares_outstanding`; a bounded 5-symbol
run recovered 5/5. Full `--all` run: 310/323 fallback attempts succeeded,
raising coverage to **92.80% (2,254/2,429)** -- up from the original
70.98% across three real, measured rounds (window widening, extraction
bug fix, Massive fallback), none of them guessed. Below Finnhub's 98.76%
(ADR-030), which composes nothing and depends on one vendor instead of
two -- expected, and not a reason to prefer this path over Finnhub for
the live reconciliation chain; this composition's value is remaining
useful as the vendor-independent fallback it was scoped to be from the
start.
