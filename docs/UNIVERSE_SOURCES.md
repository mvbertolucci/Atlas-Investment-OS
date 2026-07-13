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
