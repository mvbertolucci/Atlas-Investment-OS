# Historical Price Pairing (unlocks valuation and `altman_z`)

## Purpose

`docs/SEC_EDGAR_DATA.md` closed the loop from raw SEC totals to the ratios
Atlas scores on, but explicitly left `altman_z` and every `valuation` factor
unbuilt: they need `market_cap` (price × shares outstanding), and SEC EDGAR
has no price data at all. `backtesting/price_history.py` pairs a daily
historical close-price series (Yahoo Finance, via `yfinance`) into the same
`HistoricalObservation` contract PR-032 already consumes, and
`backtesting/point_in_time_valuation.py` derives `market_cap`, `pe`, `pb`
and `altman_z` from it.

## Why Yahoo daily history

Free, no key, already a project dependency (`providers/yahoo.py`), and goes
back decades for large caps (verified live: Apple Inc. history starts
1980-12-12, 11,486 trading days). A daily close is a public, immutable-once-
settled fact with a real calendar date -- the same kind of source PR-032's
contract was designed for.

## Mapping (`backtesting/price_history`)

One `HistoricalObservation(field_name="price")` per trading day with a
valid close (`extract_price_observations`). Same conservative,
no-look-ahead convention as `sec_edgar.available_at_from_filed`: a
fechamento is only "available" from midnight UTC of the day **after** the
trade (`available_at_from_trade_date`) -- almost certainly later than the
true intraday settlement moment, never earlier.

`fetch_price_history` uses `auto_adjust=False`: it excludes Yahoo's
additional dividend adjustment, but **Yahoo/yfinance does not expose a
truly as-traded historical close through this endpoint at all** -- the
series it returns is always retroactively adjusted for stock splits, to
stay continuous for charting.

`extract_price_observations` now restores the as-traded close by multiplying
each normalized close by the cumulative product of split ratios whose effective
dates are later than that trade. This use of future events is solely a unit
conversion that removes Yahoo's retrospective normalization; it does not expose
future economic information to a historical decision.

`extract_split_records` converts the same `Stock Splits` column into explicit
`StockSplitRecord` events. Each event enters an as-of snapshot only after its
effective date and conservative next-day availability timestamp.

`extract_split_events` is also reused by the PR-034 execution-evidence adapter
to restore historical `Open` values to as-traded units. That adapter builds
observed-session/opening-price artifacts only; it does not change the `price`
observations used by scoring. See `docs/EXECUTION_EVIDENCE.md`.

## Stock-split correction for market capitalization

`shares_outstanding` (SEC EDGAR, `dei:EntityCommonStockSharesOutstanding`)
is the *real* share count reported at each filing date -- never adjusted
for a later split. `reconstruct_snapshot_frame` now retains every selected
field's `observed_on` date and calculates
`shares_outstanding_split_factor` from split events effective strictly after
the share-count observation and on or before the paired price date.

`derive_point_in_time_valuation` multiplies the reported share count by that
factor, exposes the exact result as `shares_outstanding_split_adjusted`, and
uses it in `market_cap`, `pe`, `pb` and `altman_z`. Forward splits and reverse
splits are supported. A regression test proves market-cap continuity across a
4-for-1 split while separately proving that the event is not applied before it
is effective.

A live spot check against Yahoo's Apple history around 2020-08-31 confirmed the
source behavior and conversion: the normalized 2020-08-28 close of 124.8075
was restored to the approximately 499.23 as-traded close, while the split-date
close remained 129.04 and the extracted event ratio was 4.0.

## Deriving market_cap and the valuation ratios (`point_in_time_valuation.py`)

`derive_point_in_time_valuation(frame)` computes, once `price` and
`shares_outstanding` are both present:

- `shares_outstanding_split_adjusted = shares_outstanding × split_factor`
- `market_cap = price × shares_outstanding_split_adjusted`
- `pe = market_cap / net_income`, only when `net_income > 0` (a P/E is
  conventionally not reported, and never negative, for a loss-making
  company -- feeding a negative value into a `higher_is_better: false`
  factor would score a loss as "cheap", not flag a problem)
- `pb = market_cap / total_equity`
- `altman_z`, mirroring `analytics/fundamentals.py::_compute_altman_z`'s
  exact five weighted terms, now with a real `market_cap` term instead of
  the term being entirely absent

Same `_assign_if_absent` safety as `point_in_time_fundamentals.py`: never
overwrites a value the input frame already supplies.

**Not computed here:** `forward_pe` and `peg` (need analyst estimates, no
free point-in-time source integrated) and `ev_ebitda` (no live formula in
`analytics/mapper.py` to mirror -- the live pipeline passes through
Yahoo's own `enterpriseToEbitda` rather than computing one). `ev_ebit`,
`free_cash_flow`, `fcf_yield` and `shareholder_yield` are now derived in
`backtesting/point_in_time_valuation.py`, from `long_term_debt`,
`cash_and_equivalents`, `operating_cash_flow`, `capital_expenditures`,
`dividends_paid` and `repurchase_of_stock` (see `docs/SEC_EDGAR_DATA.md`).
The `timing` factor family (`rsi_14`, `momentum_3m/6m/12m`,
`distance_52w_high`) needed the *whole* price series available at each
cutoff, not one point-in-time value; it reuses this same paired series in
`backtesting/point_in_time_timing.py` -- see that module and
`docs/ATLAS_CONTEXT.md` for the continuous, split-adjusted series it
reconstructs.

## Verified end to end against real, live data

Apple and Microsoft, most recent decision date available
(`as_of` picking each company's latest available fundamentals and paired
price):

| | AAPL | MSFT |
|---|---|---|
| `market_cap` | ~$4.1T | ~$3.1T |
| `pe` | 57.4 | 31.4 |
| `pb` | 38.6 | 7.4 |
| `altman_z` | 10.9 (safe zone) | 8.2 (safe zone) |
| Investment Score | 48.4 (AVOID) | 58.9 (HOLD) |
| Model Confidence | 40.0% | 40.0% |

Model Confidence rose from ~32.5% (the pre-valuation SEC-only replay) to
40.0% now that the `valuation` factor family is partially populated --
concrete, measured evidence the loop got more complete, not just structurally
different. Apple's unusually high `pb` is a real, known characteristic of
its balance sheet (aggressive buybacks have driven book equity very low
relative to market cap), not a computation error.

## Compliance

Uses only Yahoo Finance's public historical-quotes endpoint via `yfinance`
(already a project dependency for the live pipeline), the same way
`providers/yahoo.py` already does.
