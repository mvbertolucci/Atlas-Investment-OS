# ADR-035 — Wikipedia "Selected changes" table as a real source for historical S&P 500 membership (proof of concept)

**Status:** Proposed (parser only, not integrated)
**Date:** 2026-07-18

## Context

`docs/ANALYTICAL_ROADMAP.md` and `docs/WALK_FORWARD_BACKTEST.md` name real
historical index-membership reconstruction as the hardest open blocker for
running PR-033/PR-034 against a real broad dataset -- no free source was
known to exist. `universe/sources.py` already scrapes the same Wikipedia
page (`SP500_CONSTITUENTS_URL`) for *current* constituents; the same page
also carries a second wikitable, "Selected changes to the list of S&P 500
components" (`id="changes"`), with `Effective Date`, `Added` (ticker +
security), `Removed` (ticker + security) and `Reason` per row.

## Decision (scope: parser only)

1. `universe/sp500_changes.py::parse_sp500_changes` -- a pure function,
   stdlib `html.parser.HTMLParser` only (no new dependency, matches
   `universe/sources.py`'s existing `_ConstituentsTableParser` pattern:
   target the table by its stable `id` attribute). The table's two header
   rows collapse to the same cell count as data rows once colspan/rowspan
   are ignored, so data rows are read by fixed position
   (date/added-ticker/added-security/removed-ticker/removed-security/
   reason), not a header-name dict lookup.
2. `fetch_sp500_changes` fetches and parses the live page, reusing the same
   URL constant as the constituents fetcher.
3. Deliberately does **not** yet reconstruct `backtesting.point_in_time.
   UniverseMembership` intervals from these changes, and does not wire into
   any collector, pipeline or CLI. This ADR proves the source is real and
   parseable; turning a change log into non-overlapping per-symbol
   membership intervals (handling a change with only one side populated,
   same-day multiple changes, and the "baseline membership at the earliest
   covered date" problem this log alone doesn't solve) is separate,
   larger, and explicitly out of scope here.

## Consequences

- Live-verified against the real page (2026-07-18): 407 changes parsed,
  1976-07-01 through 2026-06-30. Cross-checked against a real, independently
  known event -- Tesla's actual S&P 500 addition date, 2020-12-21 -- and the
  parser reproduced it exactly (`added_ticker="TSLA"`, that date).
- Density by decade measured, not assumed: 1970s 2, 1990s 8, 2000s 43,
  **2010s 218**, 2020s 136 (partial). The table's own heading says
  "Selected" changes, not "Complete" -- confirmed genuinely sparse before
  ~2000, but dense for the 2010s-2020s window, which is also the only
  window SEC XBRL point-in-time fundamentals (this repo's other real
  constraint, per `docs/SEC_EDGAR_DATA.md`) can realistically cover. The
  two constraints happen to align on the same usable window.
- 6 new offline tests (`tests/test_sp500_changes.py`), synthetic fixtures
  shaped like the real measured markup, no live network call in the test
  suite itself. 998 tests green.
- No governed scoring, no production wiring, no new external dependency.

## Rollback

Delete `universe/sp500_changes.py` and its test file. Nothing else imports
either.

## Next step (not done here)

Reconstructing actual `UniverseMembership` intervals from this change log --
and separately solving the "membership at the earliest date this log
reliably covers" baseline problem -- remains open, tracked in
`docs/BACKLOG.md`.
