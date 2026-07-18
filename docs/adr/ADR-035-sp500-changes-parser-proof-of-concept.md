# ADR-035 — Wikipedia "Selected changes" table as a real source for historical S&P 500 membership (proof of concept)

**Status:** Proposed (parser + reconstruction proven, not integrated)
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
3. `reconstruct_membership` turns the parsed change log into real
   `backtesting.point_in_time.UniverseMembership` intervals -- anchored on
   today's real constituent list (`universe.sources.fetch_sp500_constituents`)
   as ground truth instead of an unknown ancient baseline, walking each
   symbol's own event history to build alternating intervals. This solves
   both problems the original scope deferred (interval reconstruction and
   the baseline problem) with one mechanism: no baseline is needed when you
   already know the answer today and only need to walk backward.
   Deliberately **not** wired into any collector, pipeline or CLI yet --
   this ADR proves the reconstruction is correct, not that it is ready for
   production use.

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
- `reconstruct_membership` live-verified against the real change log and
  real current constituents across five window-start dates. Two real data
  anomalies found and handled explicitly rather than guessed or crashed
  on: AGN removed twice (2015, 2020) with no recorded re-addition between
  -- reported as ambiguous (`anomalous_symbols`), not resolved; FOXA
  removed and added on the *same* effective date (2019-03-19, the
  Disney/Fox transaction: 21st Century Fox out, Fox Corporation in, same
  reused ticker) -- fixed generically by sorting same-date events
  remove-before-add, not by comparing security names, so the outgoing
  entity's interval closes before the incoming one's opens.
- Measured, not assumed: reconstruction is **fully consistent** (zero
  anomalies, zero missing, zero unexpected symbols vs. the real current
  list) for every window starting 2018-01-01 or later. 2015-01-01 has
  exactly one known ambiguity (AGN). 2010-01-01 introduces three more real
  ambiguities and four symbols the log's data alone cannot close out
  correctly that far back. This means any validation window from
  2015-2018 onward -- comfortably covering the SEC-XBRL-viable range this
  repo's other real constraint already limits point-in-time fundamentals
  to -- can use this reconstruction with a *proven*, not assumed,
  integrity guarantee.
- 15 new offline tests (`tests/test_sp500_changes.py`), synthetic fixtures
  shaped like the real measured markup (including both real anomalies
  found), no live network call in the test suite itself. 1,007 tests
  green.
- No governed scoring, no production wiring, no new external dependency.

## Rollback

Delete `universe/sp500_changes.py` and its test file. Nothing else imports
either.

## Next step (not done here)

Wiring `reconstruct_membership`'s output into an actual `PointInTimeDataset`
and running walk-forward/PR-034 against a real reconstructed universe
remains open, tracked in `docs/BACKLOG.md`.
