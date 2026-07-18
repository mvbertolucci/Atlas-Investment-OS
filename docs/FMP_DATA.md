# Free FMP secondary data

## Purpose

`providers/fmp.py` uses the personal-use FMP Basic plan without a paid
subscription. It provides independent evidence for:

- `market_cap`, from the current Market Capitalization endpoint;
- `enterprise_value`, derived as current FMP market cap plus the latest FMP
  reported debt minus cash;
- free-float shares, consumed only as the denominator of the governed
  `short_float` calculation.

Massive supplies dated short-interest shares. The composed secondary derives
`short_float = Massive short_interest / FMP floatShares` only when the two
observation dates are no more than 45 days apart.

## Security and evidence

- The key is loaded from `FMP_API_KEY` or the ignored
  `config/provider_secrets.json` field `fmp_api_key`.
- Authorization uses the request header, so the key is not placed in the URL.
- The key is absent from normalized records, errors and immutable snapshots.
- FMP and the composed Massive + FMP record receive separate raw snapshots and
  per-field evidence.
- Enterprise Value retains the balance-sheet component period in its evidence
  detail while its valuation observation date follows current market cap.

## Free-plan boundary

The FMP Basic plan currently documents 250 calls per day. A normal ticker,
watchlist or portfolio run fits this budget, but a 2,429-company universe must
not use the per-symbol adapter directly. Broad-universe use requires batch
market-cap and all-float ingestion plus a persistent cache and resumable quota
budget. Until that orchestration exists, the official stored broad scoring
reference remains independent of live FMP confirmation coverage.

## Endpoints

- `GET /stable/market-capitalization`
- `GET /stable/enterprise-values`
- `GET /stable/shares-float`
- validated but not yet orchestrated: market-capitalization batch and all
  shares-float endpoints

Official references:

- <https://site.financialmodelingprep.com/developer/docs>
- <https://site.financialmodelingprep.com/pricing-plans>
