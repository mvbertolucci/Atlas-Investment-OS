# SEC EDGAR Historical Data (real acquisition, first bounded slice)

## Purpose

The first concrete step of "acquire a real, versioned, point-in-time-correct
historical dataset" (the open thread named in `docs/ATLAS_CONTEXT.md` after
PR-033). `backtesting/sec_edgar.py` converts SEC EDGAR's XBRL structured
filing data into the exact `HistoricalObservation` contract PR-032/033
already consume -- proven against **real, live SEC data**, not just
synthetic fixtures.

**This delivers a small, real vertical slice, not a complete historical
dataset.** It covers 5 native fundamental concepts for one company at a
time, fetched on demand. It does not yet cover: most of Atlas's ~25
fundamental fields, derived concepts, valuation multiples, historical
index membership, historical prices, or delisting records. See "What is
covered" and "What is not" below.

## Why SEC EDGAR

Every 10-K/10-Q has a real, immutable, publicly-known filing date. There is
no free, public source for a comprehensive point-in-time historical dataset
across index-membership/prices/delistings (see `docs/UNIVERSE_SOURCES.md`'s
own note on Russell 3000/Wilshire 5000 having no free constituent list --
the same absence-of-free-source problem applies here), but SEC EDGAR's
structured XBRL API is free, requires no API key, and its `filed` date is
exactly the `available_at` PR-032's contract needs -- arguably a more
rigorous source than a paid vendor's own point-in-time claim, since every
value traces back to a named, independently-verifiable accession number.

## API

- `GET https://www.sec.gov/files/company_tickers.json` — bulk ticker→CIK
  map (~9,300 entries as of this writing), cacheable, updated daily.
- `GET https://data.sec.gov/api/xbrl/companyfacts/CIK{cik10}.json` — every
  XBRL fact ever reported by a company, organized by taxonomy and tag.
- **Rate limit:** 10 requests/second per IP. **Required:** a `User-Agent`
  header identifying the requester (name/contact), per SEC's fair-use
  policy -- not an API key, just an identifying header on every request.

## Mapping (`backtesting/sec_edgar.TAG_TO_FIELD`)

| XBRL tag (us-gaap) | Atlas field |
|---|---|
| `Assets` | `total_assets` |
| `NetIncomeLoss` | `net_income` |
| `Revenues` | `total_revenue` |
| `AssetsCurrent` | `current_assets` |
| `LiabilitiesCurrent` | `current_liabilities` |

Deliberately small and **native-tag-only** for this increment. A concept
absent from this table is simply absent from the output -- never
approximated or backfilled.

## `available_at` convention

SEC EDGAR gives only the filing **date** (`filed`), not an intraday
timestamp. To never risk same-day look-ahead, a filing's contents are
treated as available starting **midnight UTC of the day after** it was
filed (`backtesting.sec_edgar.available_at_from_filed`). This is a
deliberate, documented, conservative choice, not a precise fact -- it is
almost certainly later than the true intraday availability moment, never
earlier.

## Revisions

Each fact carries its own accession number (`accn`) and `filed` date. A
10-K/A (amendment/restatement) gets its own `accn`/`filed`, so both the
original and the restated value are kept as separate observations --
`PointInTimeDataset.as_of` already picks the correct one for any given
cutoff (this is exactly the mechanism PR-032 built; `sec_edgar.py` just
feeds it real data).

## What is covered

- `extract_observations(symbol, company_facts)`: pure conversion, tested
  with synthetic fixtures shaped like the real API response
  (`tests/test_sec_edgar.py`) -- tag-to-field mapping, form-type filtering
  (10-K/10-Q only; 8-K exhibits and other XBRL-carrying forms are
  excluded), identity deduplication, and multi-revision handling verified
  end to end through the real `PointInTimeDataset`.
- Verified manually against **real, live data** for Apple Inc.: 647
  observations extracted across the 5 tags, correct point-in-time
  reconstruction via `as_of`, real dollar figures matching Apple's actual
  balance-sheet scale.

## What is not covered (explicit follow-up, not silently assumed)

- **Most Atlas fundamentals.** Only 5 of roughly 25 fields Atlas's scoring
  reads (see `analytics/fundamentals.py`, `analytics/mapper.py`) have a
  mapping. Missing native concepts (e.g. `GrossProfit`,
  `LongTermDebtNoncurrent`, `InterestExpense`,
  `RetainedEarningsAccumulatedDeficit`,
  `PaymentsForRepurchaseOfCommonStock`) are a straightforward table
  extension.
- **Derived concepts.** `EBIT` and `Working Capital` are not native SEC
  tags; EBIT is commonly approximated by `OperatingIncomeLoss`, Working
  Capital by `AssetsCurrent - LiabilitiesCurrent` -- a deliberate design
  decision to make explicitly, not silently fold into the tag table.
- **Valuation multiples** (PE, PB, EV/EBITDA, PEG, dividend/buyback
  yields). SEC EDGAR has no price data at all; these need a historical
  price series (Yahoo's daily history is not restated the way fundamentals
  are, so it is a reasonable pairing) matched to the same historical date
  as the fundamentals -- a separate design problem, not started.
- **Historical index membership.** Still unresolved (see
  `docs/UNIVERSE_SOURCES.md`); SEC EDGAR does not carry index constituency
  at all.
- **Delisting records with return treatment.** Not sourced from SEC EDGAR
  in this increment.
- **Bulk/checkpointed collection across many tickers.** Today's functions
  fetch one company at a time, on demand -- there is no batch collector
  analogous to `universe/collector.py`'s resumable, checkpointed design
  yet. Building one is the natural next step once tag coverage is wider.
- **XBRL taxonomy drift.** Tag names have changed across years for some
  concepts (e.g. revenue tags evolved); the 5 tags mapped here are stable,
  long-standing ones, but wider coverage will need to handle
  tag-name variants per era.

## Compliance

Uses only SEC EDGAR's public, free, no-key API with an identifying
`User-Agent`, per its documented fair-use policy. No credentials, no paid
service, no scraping outside the documented endpoints.
