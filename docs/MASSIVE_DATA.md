# Massive secondary market data

## Purpose

`providers/massive.py` is the optional independent source for fields that SEC
Company Facts does not report:

- `market_cap`;
- `enterprise_value`;
- `short_float`, derived as `short_interest / free_float`.

The adapter uses Massive's daily financial-ratios, biweekly FINRA short-interest
and free-float endpoints. It never treats free float itself as short float.
Short interest and free float must have observation dates no more than 45 days
apart; otherwise `short_float` is `unavailable` rather than estimated.

## Safety and evidence

- Disabled by default with `massive_secondary_enabled: false`.
- The key is loaded from `MASSIVE_API_KEY` or the ignored
  `config/provider_secrets.json` field `massive_api_key`.
- The API key is not included in normalized records or immutable snapshots.
- SEC and Massive use separate bounded clients, typed failures and raw
  snapshots. Failure of either secondary does not discard valid Yahoo data or
  prevent the other secondary from running.
- Each secondary declares only the critical fields it can compare. Fields with
  no configured capable source stay explicitly `secondary_unavailable`.

## Configuration

1. Create `config/provider_secrets.json` from
   `config/provider_secrets.example.json`.
2. Add the personal Massive API key locally.
3. Confirm that the chosen plan permits the Financial Ratios endpoint.
4. Set `massive_secondary_enabled` to `true` in local settings.
5. Run a bounded single-symbol check before enabling portfolio/watchlist runs.

The committed default remains disabled because no credential or subscription
may be inferred. Massive currently documents Short Interest and Float in its
stocks offering, while Financial Ratios is plan-selective. The Float endpoint
is marked experimental, so response-contract tests must be reviewed if Massive
changes its versioned path or fields.

## Endpoints

- `GET /stocks/financials/v1/ratios`
- `GET /stocks/v1/short-interest`
- `GET /stocks/vX/float` (experimental)

See the current official documentation before purchase or activation:

- <https://massive.com/docs/rest/stocks/fundamentals/ratios>
- <https://massive.com/docs/rest/stocks/fundamentals/short-interest>
- <https://massive.com/docs/rest/stocks/fundamentals/float>
