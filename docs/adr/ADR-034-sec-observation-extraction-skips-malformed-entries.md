# ADR-034 — A malformed SEC XBRL entry no longer aborts a company's whole extraction

**Status:** Accepted
**Date:** 2026-07-18

## Context

Investigating why the broad market-cap composition run (ADR-031) had 128
SEC fetch errors found the root cause was not missing data but an
over-strict failure mode in shared code: `backtesting/sec_edgar.py::
extract_observations` builds a `HistoricalObservation` per XBRL fact across
~17 tracked fields per company. `HistoricalObservation` correctly rejects
an entry whose `available_at` (derived from `filed`) precedes its
`observed_on` (the `end` period) -- you can't know about a period before it
exists. That rejection is right; propagating it uncaught was not: a single
malformed entry in *any one* of the ~17 fields raised out of the whole
function, discarding every other field's perfectly good observations for
that company.

Classified all 128 real failures: 78 were this exact pattern (in fields as
varied as `total_assets` for AGM, `dividends_paid` for ALGT, `net_income`
for AMSC -- never the field actually being sought), 48 were HTTP 404 on
`companyfacts` for closed-end funds that file N-CSR/N-2 instead of 10-K/
10-Q XBRL (legitimate absence, not a bug), 2 were genuine CIK-not-found.

This directly contradicted the function's own documented principle ("um
conceito ausente fica simplesmente ausente, nunca aproximado") -- a single
odd data point was turning into total data loss for that company instead of
absence of just that one point.

## Decision

Catch the `ValueError` per entry inside `extract_observations`'s loop and
skip only that entry, instead of letting it propagate. Every other field's
valid observations for the same company are unaffected. No new data is
invented; a field that has no usable entry after skipping remains absent,
exactly as already documented.

## Consequences

- Live-verified against six real, previously-failing symbols: ADBE, CL,
  AFL, ALGT and AMSC now return real `shares_outstanding` (the field
  extraction previously never reached because an unrelated field aborted
  first). AGM correctly still returns `None` -- it genuinely does not
  report `shares_outstanding`, and the fix does not invent one; only the
  unrelated `total_assets` violation stopped blocking it.
- Broad market-cap composition coverage rose from 76.99% (1,870/2,429,
  ADR-031's widened-window number) to **80.03% (1,944/2,429)**. Remaining
  fetch errors dropped from 128 to 50 (48 closed-end funds with no 10-K/
  10-Q XBRL + 2 CIK-not-found) -- both legitimate absences this fix
  correctly leaves alone.
- Shared code: this also affects `backtesting/sec_edgar_collector.py`'s
  checkpointed batch collection and, transitively, point-in-time replay
  (`backtesting/point_in_time_fundamentals.py`, `walk_forward.py`) --
  those paths were silently losing whole companies' worth of data to the
  same single-bad-field failure mode. Full backtesting test suite green
  (987 tests, 1 new) after the change; nothing depended on the old
  abort-on-first-violation behavior.
- No governed scoring weight, threshold or formula change -- this is
  extraction robustness only.

## Rollback

Remove the `try`/`except ValueError` around the `HistoricalObservation`
construction in `extract_observations`, restoring abort-on-first-violation.
No other code depends on the new skip behavior specifically (callers only
see a shorter or equal-length tuple of observations either way).
