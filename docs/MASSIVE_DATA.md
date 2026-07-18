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

## Cache, resumption and coverage

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
stop the current batch instead of generating repeated errors. The first live
run hit HTTP 429 after five calls at the old rate; those five were retained.
After adopting the official limit, the resumed five-symbol batch completed
without errors. Current measured checkpoint: 10/2,429 available (0.41%); this
is progress, not a broad coverage claim.

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

Official references:

- <https://massive.com/pricing?product=stocks>
- <https://massive.com/docs/rest/stocks>
