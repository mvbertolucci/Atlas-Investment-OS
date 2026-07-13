# Point-in-Time Historical Data Contract

## Purpose

This contract defines the minimum historical evidence Atlas must have before a
walk-forward result can be called point-in-time. It prevents current values,
later revisions and current constituent lists from being projected backward.

The executable contract lives in `backtesting/point_in_time.py`. PR-032 defines
and validates the data boundary only; it does not calculate a backtest,
portfolio return or performance claim. That execution belongs to PR-033 and
PR-034.

## Decision cutoff

Every reconstructed decision has one timezone-aware `decision_at` timestamp.
All timestamps are normalized to UTC and naive timestamps are rejected. A
record is visible only when its publication or public-knowledge timestamp is
less than or equal to the cutoff.

`known_at` and `available_at` mean when the information was publicly available,
not when Atlas later downloaded an archive. A future ingestion manifest may
record collection time separately, but it cannot replace source availability.

## Historical observations

Each `HistoricalObservation` is immutable and contains:

- normalized symbol and field name;
- value;
- `observed_on`, the economic or market observation date;
- `available_at`, the first timestamp at which that exact value was public;
- attributed source;
- source-specific `revision_id`.

`available_at` cannot precede `observed_on`. Duplicate identities — symbol,
field, observation date and revision — are invalid. Revisions are appended, not
overwritten.

At a decision cutoff Atlas:

1. excludes observations not yet available;
2. excludes observation periods after the decision date;
3. selects the newest available observation period per symbol and field;
4. within that period, selects the latest revision available at the cutoff.

Missing values stay missing. The contract does not backfill, carry data across
symbols or silently substitute current fundamentals.

## Constituent history

`UniverseMembership` uses a half-open interval:

```text
effective_from <= decision date < effective_to
```

An absent `effective_to` means the interval remains open. Additions, removals
and later re-entries must be retained as separate non-overlapping intervals.
Current constituents alone are not historical evidence. A membership interval
is usable only if its `known_at` source timestamp is at or before the decision
cutoff.

The 2026-07-13 research snapshot remains valid for current research collection,
but it must not be used as the membership set for earlier decisions.

## Stock splits and unit consistency

`StockSplitRecord` stores the symbol, effective date, ratio, conservative
availability timestamp and source. Forward and reverse ratios are supported;
duplicate events for the same symbol and date are invalid. A split enters an
as-of snapshot only after it is both effective and available.

Yahoo's historical close is normalized retrospectively for later splits while
SEC shares outstanding are reported in the units valid on the observation
date. Atlas first restores Yahoo closes to their as-traded units. During frame
reconstruction it then applies only splits effective after the selected share
observation and on or before the selected price observation. Future events are
therefore used only to undo vendor unit normalization, never as economic input
to an earlier decision. See `docs/PRICE_HISTORY_DATA.md`.

## Delistings

Every terminal security event requires a `DelistingRecord` with effective date,
last trading date, source availability timestamp and explicit return treatment:

- `cash`: terminal cash proceeds are required;
- `zero`: terminal value is explicitly zero;
- `successor`: a successor symbol is required;
- `unresolved`: evidence is incomplete and must remain visible.

Rows may never be dropped merely because a symbol disappears from the current
provider. PR-033 must propagate unresolved events as incomplete validation, and
PR-034 must disclose how each terminal event affects return calculations.

## Executable snapshot

`PointInTimeDataset.as_of(decision_at)` produces a deterministic `AsOfSnapshot`
containing only information visible and effective at the cutoff:

- active constituent symbols;
- one latest eligible observation per symbol and field;
- known, effective delisting events.

The snapshot is the input boundary planned for the walk-forward engine. It does
not rank companies, construct positions or calculate returns by itself.

## Required provenance for PR-033

A historical input set must be versioned and attributable. Before walk-forward
execution, its manifest must pin:

- source name and source version or retrieval artifact hash;
- benchmark and constituent-history source;
- decision calendar and timezone;
- observation and availability fields;
- revision policy;
- delisting coverage and unresolved-event count;
- Atlas code revision and governed configuration hashes.

If any required field is unavailable, the affected decision is incomplete; it
must not be repaired with present-day data or silently removed from results.

## Out of scope

PR-032 does not add historical-data acquisition, provider credentials,
walk-forward scheduling, transaction costs, benchmark returns, portfolio
performance, calibration or live trading. Those remain bounded later tasks.
