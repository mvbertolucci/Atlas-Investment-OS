# Massive secondary market data

## Purpose

`providers/massive.py` supplies dated Short Interest for the governed
`short_float` risk metric. When FMP is active, the adapter intentionally skips
the denied Massive Financial Ratios and experimental Float endpoints. It
derives `short_float` from Massive Short Interest and FMP Float only when their
observation dates are no more than 45 days apart.

## Safety and evidence

- Enabled for this installation with `massive_secondary_enabled: true`; without
  a local key the provider stays inert and emits a configuration warning.
- The key is loaded from `MASSIVE_API_KEY` or the ignored
  `config/provider_secrets.json` field `massive_api_key`.
- The API key is not included in normalized records or immutable snapshots.
- SEC, FMP and Massive use separate bounded clients, typed failures and raw
  snapshots. Failure of either secondary does not discard valid Yahoo data or
  prevent the other secondary from running. The composed evidence names both
  Massive and FMP rather than attributing `short_float` to either alone.
- Each secondary declares only the critical fields it can compare. Fields with
  no configured capable source stay explicitly `secondary_unavailable`.

## Configuration

1. Create `config/provider_secrets.json` from
   `config/provider_secrets.example.json`.
2. Add the personal Massive API key locally.
3. Configure the free FMP key described in `docs/FMP_DATA.md`.
4. Set both secondary flags to `true` in local settings.
5. Run a bounded single-symbol check before portfolio/watchlist runs.

The protected personal keys were validated on 2026-07-17. AAPL `short_float`
was confirmed from 2026-06-30 Massive Short Interest and 2026-07-15 FMP Float.
No paid Massive endpoint is required while FMP is active.

## Endpoints

- `GET /stocks/v1/short-interest`
- fallback only: `GET /stocks/vX/float` (experimental)

Official documentation:

- <https://massive.com/docs/rest/stocks/fundamentals/ratios>
- <https://massive.com/docs/rest/stocks/fundamentals/short-interest>
- <https://massive.com/docs/rest/stocks/fundamentals/float>
