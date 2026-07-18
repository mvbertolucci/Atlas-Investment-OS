# Massive secondary market data

## Purpose

`providers/massive.py` uses only endpoints available to the personal Stocks
Basic plan:

- Ticker Details supplies current `market_cap` and outstanding-share metadata;
- Short Interest supplies the dated numerator of `short_float`;
- native Float is the preferred dated denominator;
- FMP Float is used only when native Float is absent or more than 45 days from
  Short Interest;
- `enterprise_value` composes Massive market cap with aligned SEC debt/cash.

No Financial Ratios request is made.

## Broad free-float snapshot

Massive Float supports market-wide pagination, so Atlas no longer spends one
request per ticker to obtain the denominator of `short_float`. The command
below downloads all pages, checkpoints each successful page atomically and
publishes coverage against `US_MARKET_ELIGIBLE`:

```powershell
.\.venv\Scripts\python.exe -m providers.massive_float_prefetch
```

The resumable snapshot is stored in the ignored file
`data/provider_cache/massive_float.json`. Pagination cursors are accepted only
from `api.massive.com` stock paths, and any API key is stripped before the
cursor is persisted. A complete fresh snapshot is authoritative for absence:
normal ticker runs do not fall back to one Float request per missing symbol.

The 2026-07-17 live collection completed all seven pages without errors:

- 6,662 market records received;
- 2,364/2,429 eligible symbols matched directly (97.32%);
- hyphenated share classes such as `BRK-B` are matched to Massive's dotted
  notation (`BRK.B`);
- one additional eligible symbol has dated FMP fallback evidence, producing
  2,365/2,429 combined availability (97.37%);
- the remaining 64 symbols stay explicitly unavailable; outstanding shares
  are never substituted for free float.

## SEC public-float audit

The residual audit is reproducible with:

```powershell
.\.venv\Scripts\python.exe -m providers.sec_public_float_audit
```

SEC `dei:EntityPublicFloat` is an aggregate USD market value held by
non-affiliates, not a number of shares. Atlas extracts it from annual 10-K,
20-F and 40-F Company Facts, preserves the raw response as an immutable
SHA-256 snapshot and evaluates it against the same 45-day alignment window.
It is never divided by an assumed or current price.

The 2026-07-17 audit of all 64 residual symbols found:

- 28 positive monetary values, all stale; the newest was 290 days old;
- 30 issuers without the SEC concept in Company Facts;
- 3 zero public-float values;
- 3 unavailable provider mappings/responses;
- 0 observations eligible for conversion into free-float shares.

Structural review groups were 16 partnerships/MLPs, 8 asset managers or funds,
5 shell companies, 32 operating/recent listings and 3 unresolved issuers.
These groups are review aids, not legal classifications or automatic
`not_applicable` decisions. The ignored detailed report is written to
`output/dados/sec_public_float_audit.json`.

## Ticker Details cache and resumption

Stocks Basic documents five API calls per minute. Atlas enforces a five-call
rolling window internally and runs broad Ticker Details prefetch at 4.5 calls
per minute (`0.075/s`) to retain safety margin. Every successful response and
definitive 404 is written atomically to:

`data/provider_cache/massive_ticker_details.json`

The cache is the checkpoint. A repeated command skips fresh records and starts
at the first unresolved eligible symbol. The default invocation processes five
new symbols and updates the ignored coverage report:

```powershell
.\.venv\Scripts\python.exe -m providers.massive_prefetch
```

To continue until completion in one long process:

```powershell
.\.venv\Scripts\python.exe -m providers.massive_prefetch --all
```

At five calls per minute, a cold 2,429-symbol scan takes approximately 8.1
hours. It can be interrupted safely. Authentication and rate-limit failures
stop the current batch instead of generating repeated errors. This scan is no
longer the preferred way to collect broad free float; it remains useful for
per-company market-cap metadata until a more efficient broad derivation is
implemented.

## Broad market-cap price snapshot (Grouped Daily)

The per-symbol Ticker Details scan above is a slow way to price the whole
eligible universe (8.1 hours cold). `GET /v2/aggs/grouped/locale/us/market/
stocks/{date}` returns every US stock ticker's OHLC for one trade date in a
single Basic-plan call. Live-verified 2026-07-16: one request returned 12,452
market records and matched 2,423/2,429 eligible symbols (99.75%).

```powershell
.\.venv\Scripts\python.exe -m providers.massive_grouped_daily_prefetch --date 2026-07-16
```

The resumable snapshot is stored in the ignored file
`data/provider_cache/massive_grouped_daily.json`, keyed by trade date. A past
date's bars are immutable, so a cache hit never re-requests the network — this
cache never expires, unlike the Ticker Details or Float caches above, which
describe current state. Coverage is written to the ignored
`output/dados/massive_grouped_daily_coverage.json`.

This snapshot supplies the price leg (`close`). Composition with SEC
`shares_outstanding` into `market_cap` at scale is implemented in
`providers/market_cap_composition.py` + `market_cap_composition_prefetch`
(CLI) — see ADR-031. The full 2,429-symbol broad run composed 1,944
(80.03%), no external vendor beyond Massive+SEC; remaining gaps tracked in
`docs/BACKLOG.md`.

## Safety and evidence

- The key is loaded from `MASSIVE_API_KEY` or ignored
  `config/provider_secrets.json`.
- Keys are absent from cache, normalized records, errors and raw snapshots.
- SEC Company Facts is cached in memory per run to avoid duplicate downloads.
- Missing Float or SEC components remain unavailable; outstanding shares are
  never mislabeled as free float.
- Provider errors remain typed, retry-bounded and source-attributed.

## Endpoints

- `GET /v3/reference/tickers/{ticker}`
- `GET /stocks/v1/short-interest`
- `GET /stocks/vX/float`
- `GET /v2/aggs/grouped/locale/us/market/stocks/{date}`

Official references:

- <https://massive.com/pricing?product=stocks>
- <https://massive.com/docs/rest/stocks>
