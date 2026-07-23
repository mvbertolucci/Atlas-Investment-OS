# Research Universe Sources

## Sample overview — which universe to update, and when

Atlas works with **several distinct universe samples**, layered from the whole
listed market down to what actually gets deep, per-company fundamentals. They
are independent: each has its own source, artifact, checkpoint and refresh
command, so updating one is an explicit choice that does not touch the others.

| Sample | What it is | Size | Artifact | Refresh command |
|--------|-----------|------|----------|-----------------|
| **S&P 500 research** | Deep-collection working set for the default run; the S&P 500 | ~503 | `config/research_universe.csv` (+ checkpoint `data/research_universe_collection.json`) | `python -m universe.sources` → `python -m universe.collector` |
| **Broad US market** | Every US-listed common stock (small caps included) | ~7,093 raw | `config/research_universe_market.csv` (+ checkpoint `data/research_universe_collection_market.json`) | `python -m universe.sources --market` → `python -m universe.collector --market` |
| **US_MARKET_ELIGIBLE scoring reference** | Cross-sectional percentile base for scores (the eligible subset of the broad market) | ~2,429 eligible | `output/dados/scoring_reference_market.json` | rebuilt by the market model-portfolio build over the eligible market collection (`portfolio/model_portfolio.py`) |
| **Portfolio + watchlist** | What `run_all.py --portfolio` and the default run deep-collect for decisions | ~57 | `config/portfolio.csv` + `config/watchlist.csv` | normal `run_all.py` (fetched live per run) |
| **ADR lens** | Foreign issuers, US-listed — a policy view, not a separate collection | — | `config/universe_adr.yaml` | none: reuses the broad-market collection |

**How the layers relate.** The broad market (~7,093 listed symbols) is filtered
by eligibility (country, volume, market-cap floor, live `quote_type`) into the
**US_MARKET_ELIGIBLE** set (~2,429), which is the cross-sectional reference that
score percentiles are computed against. Separately, a **working set** is
deep-collected for fundamentals: by default the **S&P 500** (~503), and for a
decision run the **portfolio + watchlist** (~57). The number you see as
`reference_count` on a company (e.g. 2,429) is the *scoring reference size*, not
what was deep-collected that run.

**Freshness matters more than size.** As of this writing the broad-market
collection and the 2,429 reference were last built on **2026-07-13**
(reference/reports generated 2026-07-17) — so refreshing them is a real,
periodic task, not a one-off. Deciding which sample to refresh is an operational
choice; the scale/time trade-off (a single ~50-min S&P 500 run vs. a multi-hour
broad-market collection) is described per screener below.

> Note: an earlier revision of this doc said the broad-market screener "has not
> been run yet." That is stale — its checkpoint
> (`data/research_universe_collection_market.json`) and the derived
> `*_market.json` reports and scoring reference exist (built 2026-07-13/17). The
> broad-market ranking/model-portfolio step *has* run.

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

This screener's collection **has** been run (checkpoint
`data/research_universe_collection_market.json` and the derived
`research_universe_report_market.json` / `research_ranking_report_market.json` /
`scoring_reference_market.json` all exist, built 2026-07-13/17). The ~2,429-name
`US_MARKET_ELIGIBLE` scoring reference is the eligible output of this
collection. Re-running it to refresh the broad market and the reference is a
periodic operational task (see the Sample overview at the top).

## Third screener: US-listed ADRs

`config/universe_adr.yaml` is a third, independent eligibility policy for
American Depositary Receipts -- foreign-domiciled companies whose shares
trade on a US exchange in USD. Same minimum entry parameter as the broad
market screener (USD 300 million market cap, same price/volume floors).

### Why this needed a small model change, not a new data source

ADRs already trade on NASDAQ/NYSE/NYSE American/Arca/Cboe, so they are
already present in the broad-market collection above -- there is no separate
constituent source to fetch. What excluded them until now was the eligibility
*policy*: both the S&P 500 and broad-market screeners require
`allowed_countries: [United States]`, and a real ADR's Yahoo-reported `country`
is the foreign domicile (e.g. `Argentina`, `Germany`), not `United States` --
so they were always structurally excluded by that check, regardless of
market cap.

`allowed_countries` was (and remains) a strict allow-list -- there was no way
to express "any country except X". `UniversePolicy` gained an
`excluded_countries` field, and `allowed_countries` accepts an explicit `"*"`
wildcard entry (any country passes the inclusion check) which is then
filtered by `excluded_countries`. This is additive and backward-compatible:
neither the S&P 500 nor the broad-market policy uses `"*"` or
`excluded_countries`, so their behavior is unchanged (a governance test pins
this: `test_default_allow_list_behavior_is_unchanged_by_the_new_field`).

`config/universe_adr.yaml` sets `allowed_countries: ["*"]` and
`excluded_countries: [United States]` -- any foreign domicile is eligible,
US domicile explicitly is not.

### No separate collection

This screener is evaluated against the **same** broad-market collection
(`config/research_universe_market.csv` / its checkpoint) once that has been
collected -- just a different eligibility lens (`evaluate_universe`/
`rank_companies` applied with `config/universe_adr.yaml` instead of
`config/universe_market.yaml`). There is nothing to collect separately, and no
`--adr` flag on the collector. Wiring an actual ranking/model-portfolio run
under this policy is a deliberate follow-up, matching the broad-market
screener's own deferred ranking step.
