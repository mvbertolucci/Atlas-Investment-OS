# Free Finnhub secondary data

## Purpose

`providers/finnhub.py` uses the free personal Finnhub Stocks plan, no credit
card required. It supplies `market_cap` and `enterprise_value` only, both
vendor-computed absolute values returned by a single call to
`GET /stock/metric?metric=all`. No composition is needed -- unlike Massive
(market cap + SEC debt/cash) or FMP (two calls, market cap and enterprise
value separately).

The free tier does not include raw balance-sheet line items (total debt,
total cash), only ratios (`totalDebt/totalEquityAnnual`, etc.), so Finnhub
cannot feed Atlas's own Altman Z / ROIC / Interest Coverage formulas -- those
keep using SEC EDGAR components. Finnhub only claims the two fields it
supplies as vendor-computed values.

## Why it was added (ADR-030)

FMP's free daily quota (250 calls) covered only 67/2,429 eligible symbols for
market cap and 6 for enterprise value in the 2026-07-17 broad scan (see
`docs/FMP_DATA.md`). Finnhub's free tier rate-limits per minute (60, no
observed daily cap) instead of per day, so a full 2,429-symbol scan takes
roughly 45 minutes instead of being capped at a few dozen symbols. Live
verification (2026-07-18, AAPL): `/stock/metric` returned real, correctly
scaled data (`marketCapitalization: 4,860,046.5` -> $4.86T once converted
from millions) with no premium-plan error.

Ordering in `application/collection.py`'s live per-symbol secondary chain
changed: Finnhub now goes first, so it claims `market_cap`/`enterprise_value`
confirmation ahead of Massive. Massive still runs unconditionally and still
claims `short_float` (its strongest field, ~97% broad coverage via the
market-wide Float snapshot) and still composes its own SEC-based
`enterprise_value` internally for its own record/evidence trail, even though
that value is no longer the one used for reconciliation. FMP is unchanged --
still the accepted Float fallback inside Massive's composition, and its own
`market_cap`/`enterprise_value` claim was already excluded from reconciliation
before this change (Massive claimed those fields first).

Live-verified against the real per-symbol chain (AAPL, 2026-07-18): Yahoo
already had a live `market_cap` (so nothing was overwritten), but
`field_evidence.market_cap.confirmation_status == "confirmed"` and
`confirmed_by == "Finnhub"` -- Finnhub was queried and is now the recorded
confirming source. `secondary_raw_snapshots` included `Finnhub` alongside
`SEC EDGAR Company Facts` and `Massive`, proving all three ran.

## Broad prefetch

```powershell
.\.venv\Scripts\python.exe -m providers.finnhub_prefetch --limit 55
```

Cache-first and resumable like the other broad prefetch CLIs: a symbol
already fresh in `data/provider_cache/finnhub.json` (2-day TTL) is skipped, so
repeated invocations make progress without re-requesting cached symbols.
Default batch size is 55 per invocation (matches the 55/minute pacing, one
minute of calls); `--all` runs until the whole eligible universe is covered
(~44 minutes cold). Coverage is written to the ignored
`output/dados/finnhub_coverage.json`. Bounded live check (2026-07-18, 20
symbols): 0 errors, all 20 cached and available.

## Safety and evidence

- The key is loaded from `FINNHUB_API_KEY` or the ignored
  `config/provider_secrets.json` field `finnhub_api_key`.
- Authorization uses a query parameter (`token`), the only mechanism Finnhub's
  REST API supports; the key never appears in cached payloads or evidence
  (only path/params without the token are logged).
- `market_cap`/`enterprise_value` are converted from Finnhub's millions to
  absolute USD at the boundary, matching every other provider's unit
  contract; nothing downstream needs to know Finnhub reports in millions.
- Missing or non-numeric metric values become `field_evidence` status
  `unavailable`, never a fabricated zero.

## Endpoints

- `GET /stock/metric?metric=all`

Official references:

- <https://finnhub.io/pricing>
- <https://finnhub.io/docs/api>
