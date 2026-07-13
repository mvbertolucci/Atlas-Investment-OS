# SEC EDGAR Historical Data (real acquisition, first bounded slice)

## Purpose

The first concrete step of "acquire a real, versioned, point-in-time-correct
historical dataset" (the open thread named in `docs/ATLAS_CONTEXT.md` after
PR-033). `backtesting/sec_edgar.py` converts SEC EDGAR's XBRL structured
filing data into the exact `HistoricalObservation` contract PR-032/033
already consume -- proven against **real, live SEC data**, not just
synthetic fixtures.

**This delivers a small, real vertical slice, not a complete historical
dataset.** It covers 15 native fundamental concepts, now collected in
checkpointed, resumable batches across many tickers at once
(`backtesting/sec_edgar_collector.py`, mirroring `universe/collector.py`'s
design). It does not yet cover: derived concepts requiring several raw
components, valuation multiples, historical index membership, historical
prices, or delisting records. See "What is covered" and "What
is not" below.

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

## Mapping (`backtesting/sec_edgar.FIELD_TAG_CANDIDATES`)

| Atlas field | XBRL tag candidates (taxonomy:tag, priority order) |
|---|---|
| `total_assets` | `us-gaap:Assets` |
| `net_income` | `us-gaap:NetIncomeLoss` |
| `total_revenue` | `us-gaap:Revenues`, `us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax`, `us-gaap:SalesRevenueNet` |
| `current_assets` | `us-gaap:AssetsCurrent` |
| `current_liabilities` | `us-gaap:LiabilitiesCurrent` |
| `gross_profit` | `us-gaap:GrossProfit` |
| `long_term_debt` | `us-gaap:LongTermDebtNoncurrent`, `us-gaap:LongTermDebt` |
| `retained_earnings` | `us-gaap:RetainedEarningsAccumulatedDeficit` |
| `total_liabilities` | `us-gaap:Liabilities` |
| `interest_expense` | `us-gaap:InterestExpense` |
| `tax_provision` | `us-gaap:IncomeTaxExpenseBenefit` |
| `pretax_income` | `us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest`, `us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments` |
| `repurchase_of_stock` | `us-gaap:PaymentsForRepurchaseOfCommonStock` |
| `operating_income` | `us-gaap:OperatingIncomeLoss` (kept under this name, not silently renamed to `ebit` -- see below) |
| `shares_outstanding` | `dei:EntityCommonStockSharesOutstanding`, `us-gaap:CommonStockSharesOutstanding` |

Deliberately **native-tag-only**. A concept absent from this table is
simply absent from the output -- never approximated or backfilled.

**Multiple candidates per field are all extracted and merged**, not just
the first one with data: the same company can use different tags in
different eras (e.g. many companies switched from `Revenues` to
`RevenueFromContractWithCustomerExcludingAssessedTax` around the 2018
revenue-recognition standard change). Taking only the first candidate with
*any* data would silently drop the part of a company's history tagged
under the other name. `shares_outstanding` is read from the `dei`
taxonomy first (where it is conventionally reported), falling back to
`us-gaap`.

Verified against real, live SEC data for Apple Inc.: 2,350 observations
across these 15 fields (up from 5/647 in the first increment), values
matching Apple's real financial scale (e.g. gross profit ~$124B, shares
outstanding ~14.7B, operating income ~$86.7B as of the most recent 10-Q).

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

## Checkpointed multi-ticker collection

`backtesting/sec_edgar_collector.py` mirrors `universe/collector.py`'s
resumable, checkpointed batch design, applied to SEC EDGAR instead of
Yahoo:

```powershell
$env:SEC_EDGAR_USER_AGENT = "Your Name (contact: you@example.com)"
.\.venv\Scripts\python.exe -m backtesting.sec_edgar_collector --batch-size 10
```

- Defaults to `config/watchlist.csv` (Atlas's real, current watchlist) as
  the ticker list, and `data/sec_edgar_collection.json` as the checkpoint
  (both overridable via `--tickers-file` / `--state`).
- **`--user-agent` has no hardcoded default in source** -- it is required,
  read from the `SEC_EDGAR_USER_AGENT` environment variable by default (or
  `--user-agent` explicitly). Personal contact information never lives in
  committed code.
- One checkpoint write per ticker (not just at batch end), atomic
  temp-file-then-replace with retry, exactly like `universe/collector.py`.
  Safe to interrupt and resume; already-collected symbols are skipped, and
  every failure is recorded with its real error message, never silently
  dropped.
- **A ticker with no CIK is an explicit failure, not a skip.** Verified
  against Atlas's real watchlist: `BEEF3.SA` (Minerva, a B3-only listing
  with no SEC registration) correctly fails with `"CIK não encontrado"` --
  SEC EDGAR only covers SEC-registered filers (US-listed companies and
  foreign private issuers that file with the SEC), not every ticker in
  Atlas's watchlist. This is an expected, honest limitation, not a bug: a
  foreign-domiciled ADR (SEC-registered) will succeed; a foreign-exchange
  local listing (not SEC-registered) will not, and is reported as such.
  Real batch verified: `ASML`, `AVAV`, `BNTX` collected successfully in the
  same run.
- `SecEdgarCollectionState.observations()` returns real `HistoricalObservation`
  tuples straight from the checkpoint, ready to build a `PointInTimeDataset`.

## What is covered

- `extract_observations(symbol, company_facts)`: pure conversion, tested
  with synthetic fixtures shaped like the real API response
  (`tests/test_sec_edgar.py`) -- field-to-tag mapping across multiple
  candidates and taxonomies, form-type filtering (10-K/10-Q only; 8-K
  exhibits and other XBRL-carrying forms are excluded), identity
  deduplication, cross-era tag-switch merging, and multi-revision handling
  verified end to end through the real `PointInTimeDataset`.
- Verified manually against **real, live data** for Apple Inc.: 2,350
  observations extracted across the 15 fields, correct point-in-time
  reconstruction via `as_of`, real dollar figures matching Apple's actual
  financial scale.
- **XBRL taxonomy drift is now partially handled**, not just documented as
  a gap: the highest-value fields (`total_revenue`, `long_term_debt`,
  `pretax_income`, `shares_outstanding`) carry multiple candidate tags
  across the eras/taxonomies companies actually used, and all candidates
  are merged rather than only the first with data.

## What is not covered (explicit follow-up, not silently assumed)

- **Some Atlas fundamentals.** 15 of roughly 25 fields Atlas's scoring
  reads (see `analytics/fundamentals.py`, `analytics/mapper.py`) have a
  mapping. Remaining native concepts not yet mapped (e.g. per-share EPS
  tags, specific margin/ratio line items only some filers break out) are a
  straightforward table extension.
- **Derived concepts.** `EBIT` and `Working Capital` are not native SEC
  tags. `operating_income` (`OperatingIncomeLoss`) is mapped as a commonly
  used EBIT *proxy*, kept under its own name rather than silently renamed
  to `ebit`, so that decision stays visible to whoever consumes it; Working
  Capital is `current_assets - current_liabilities`, both already mapped,
  but the subtraction itself is not yet computed anywhere.
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
- **Non-SEC-registered tickers can never be collected this way.** Confirmed
  with a real batch: any ticker without a US SEC filing (e.g. a foreign
  company listed only on a local exchange, like a B3-only Brazilian stock)
  has no CIK and fails explicitly, by design -- it is not a bug to fix, it
  is a hard boundary of what SEC EDGAR can cover. Such symbols would need a
  different, non-SEC source if ever required.
- **Further tag-drift coverage.** Multi-candidate merging is applied to
  the fields most likely to need it; other concepts still use a single
  candidate tag and may need alternates added as real coverage gaps are
  found (e.g. by running the collector across many companies/eras).

## Compliance

Uses only SEC EDGAR's public, free, no-key API with an identifying
`User-Agent`, per its documented fair-use policy. No credentials, no paid
service, no scraping outside the documented endpoints.
