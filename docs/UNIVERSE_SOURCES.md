# Research Universe Sources

## Current snapshot

`config/research_universe.csv` is the reproducible research population used to
expand Atlas beyond the personal watchlist. The current snapshot contains 503
S&P 500 share classes as observed on 2026-07-13.

Fields include the Yahoo-compatible symbol, source symbol, company, GICS sector
and industry, headquarters, index-added date, CIK, founding information, source
URL and snapshot date. Dot-class tickers are normalized for Yahoo (`BRK.B` to
`BRK-B`, for example), while the original symbol is preserved.

## Source and attribution

The constituent table is derived from Wikipedia's public
`List of S&P 500 companies` page and retains its source URL on every record.
Wikipedia content is available under CC BY-SA; review its current terms before
redistributing a modified snapshot.

S&P Dow Jones Indices is the index operator. State Street's official SPY page
is used as an independent current-count reference because SPY seeks to track the
S&P 500, but its downloadable holdings file is not committed or redistributed
by Atlas.

This snapshot is research metadata, not an official index license, investment
recommendation or guarantee of current membership.

## Refresh

Refresh is an explicit, reviewable action rather than a silent runtime update:

```powershell
.\.venv\Scripts\python.exe -m universe.sources --output config/research_universe.csv
```

After refreshing:

1. inspect additions, removals and symbol changes;
2. verify the source and snapshot date;
3. run `tests/test_universe_sources.py` and update its pinned expectations;
4. document the membership change;
5. commit the new snapshot separately.

Historical snapshots must be retained when point-in-time validation is added;
overwriting history would introduce survivorship bias.

## Batch boundary

The source module deterministically divides the sorted universe into batches.
The configured planning size is 25 symbols, or 21 batches for 503 constituents.
This PR does not send those batches to Yahoo. Incremental collection, retry and
checkpoint behavior must be implemented and tested before broad execution is
enabled.

## Second screener: broad US market (small caps included)

`config/research_universe_market.csv` is a **separate** screener from the S&P
500 one above -- distinct snapshot, checkpoint, batch size and eligibility
policy (`config/universe_market.yaml`, `min_market_cap: 300000000` — a genuine
small-cap floor, vs. the S&P 500 screener's `1000000000`, which is really a
mid-cap-and-up floor since S&P 500 members are already large caps). Nothing
about the S&P 500 screener changes.

### Source and attribution

There is no free, public constituent list for a broad index like Russell 3000
or Wilshire 5000 (both are FTSE/Russell proprietary products). The closest
public, comprehensive US-market listing is the **NASDAQ Trader symbol
directory** (`nasdaqlisted.txt` for NASDAQ-listed securities,
`otherlisted.txt` for NYSE, NYSE American, NYSE Arca and Cboe BATS). It is a
reference/listing directory, not a fundamentals feed: it has no
sector/industry/market-cap data. That is harmless — the collector only reads
`symbol`/`name` from any constituent snapshot; sector, country, price, volume
and market cap are always fetched live from Yahoo per ticker, exactly as for
the S&P 500 screener.

Exclusion of ETFs, NextShares vehicles and Test Issues uses the explicit flags
the NASDAQ Trader files provide. Excluding preferred shares, warrants, units
and rights is **best-effort** (a conservative ticker-pattern filter, since
these files carry no dedicated flag for them) — the real, authoritative
backstop is `allowed_quote_types: [EQUITY]` in `config/universe_market.yaml`,
checked against each ticker's actual live `quote_type` from Yahoo during
scoring. Anything that slips past the constituent-list filter but is not a
true equity gets excluded there.

### Refresh

```powershell
.\.venv\Scripts\python.exe -m universe.sources --market
.\.venv\Scripts\python.exe -m universe.collector --market
```

`universe.collector --market` is resumable/checkpointed exactly like the
S&P 500 collector, reading `research_universe_market_path` /
`research_collection_market_state_path` / `research_universe_market_batch_size`
from `config/settings.json` (or explicit `--snapshot` / `--state` overrides).

### Scale expectation

The NASDAQ Trader directories list several thousand raw securities (commonly
6,000-11,000 rows across both files before filtering). After excluding
ETFs/test issues/non-equity patterns and applying the USD 300 million market-cap
floor, the eligible population is expected to still be in the low thousands —
several times larger than the 503-name S&P 500 screener. Collection will take
substantially longer and hit Yahoo rate limits more often; this is exactly why
the checkpointed, resumable, retryable collector design (built for the S&P 500
screener) matters here.

This screener's collection has not been run yet as of this writing --
`config/universe_market.yaml` and the source/collector code are in place, but
no snapshot or checkpoint file exists. Running the ranking/model-portfolio step
over this broader universe is a deliberate follow-up, not part of this
increment.
