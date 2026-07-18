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

The FMP Basic plan currently documents 250 calls per day. Atlas enforces that
limit locally, reserves 25 calls for interactive runs and persists the UTC-day
counter separately from the response cache. Market cap is fetched in batches,
float is paged, and enterprise value is resumed per supported symbol. Cache
TTLs are 2, 7 and 120 days respectively. Completed scans also cache an empty
result for unsupported symbols, preventing repeated calls from turning absence
into either false confirmation or quota waste.

Run or resume the eligible-universe prefetch with:

```powershell
.\.venv\Scripts\python.exe -m providers.fmp_prefetch
```

The live 2026-07-17 scan requested all 2,429 eligible symbols and found usable
market-cap and float records for only 67 under the configured Basic entitlement;
enterprise evidence was available for 6 before the daily prefetch ceiling was
reached (225 used, 25 reserved). HTTP 402 responses show that the free account
is not an independent broad-market confirmation source. Uncovered fields remain
explicitly unavailable/`secondary_unavailable`; they are never treated as
confirmed. The official stored broad scoring reference remains independent of
FMP coverage.

Runtime files are local and ignored by Git:

- `data/provider_cache/fmp.json`: response and negative-result cache;
- `data/provider_cache/fmp_quota.json`: daily call counter.

## Endpoints

- `GET /stable/market-capitalization`
- `GET /stable/enterprise-values`
- `GET /stable/shares-float`
- `GET /stable/market-capitalization-batch`
- `GET /stable/shares-float-all`

Official references:

- <https://site.financialmodelingprep.com/developer/docs>
- <https://site.financialmodelingprep.com/pricing-plans>
