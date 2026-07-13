# Versioned Historical Execution Evidence

## Purpose

`backtesting/execution_evidence.py` converts already-acquired Yahoo-shaped
daily bars into the explicit session and opening-price contracts consumed by
`backtesting/historical_execution.py`. The adapter is pure and offline; it
does not invoke Yahoo or the broad-market collector.

## Observed-session proxy

There is no exchange-calendar dependency in Atlas. Version 1 therefore uses
the valid daily `Open` rows of an explicit liquid reference symbol (normally
SPY) as evidence that a regular U.S. session was observed. Each row is mapped
to 09:30 `America/New_York`; `zoneinfo` converts that timestamp to UTC and
handles daylight-saving changes.

This is deliberately called `observed_reference_daily_bars`, not an official
exchange calendar. A missing reference bar means the session is absent from
the artifact. Symbol price rows on dates absent from the reference are filtered
out. The reference symbol and every row source remain explicit.

## Opening-price units

Yahoo daily OHLC bars returned with `auto_adjust=False` remain retrospectively
normalized for splits. `extract_opening_price_observations` restores each
historical `Open` to its as-traded units by multiplying only split ratios whose
effective dates are later than that session, the same unit-restoration policy
already used for historical `Close` in `backtesting/price_history.py`.

This adjustment is a unit conversion. It does not add a future economic return
to an earlier decision. Missing or non-positive openings are never invented.

## Artifact contract

`HistoricalExecutionEvidence` schema version 1 stores:

- reference symbol and timezone-aware retrieval timestamp;
- fixed calendar method, timezone, regular-open time, price field and split
  policy;
- attributed observed sessions;
- attributed opening prices by symbol and exact session timestamp.

Duplicate sessions/prices, off-session prices, manifest changes and retrieval
timestamps earlier than their evidence are rejected. JSON write/load preserves
the full contract, and the loaded artifact can feed `execute_historical_target`
directly.

## Remaining boundary

The adapter and versioned format are implemented, but no broad real execution
artifact is committed or collected by this change. A later bounded acquisition
run must fetch the reference and actually selected symbols, record retrieval
provenance and keep runtime market data outside Git. Dividend-inclusive total
returns and terminal-event evidence remain separate required inputs.
