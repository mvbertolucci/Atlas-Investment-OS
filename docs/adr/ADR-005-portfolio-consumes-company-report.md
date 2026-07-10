# ADR-005 — Portfolio consumes CompanyReport

## Status

Accepted

## Decision

The Portfolio layer consumes `CompanyReport` objects instead of raw scoring DataFrames.

## Consequences

- Portfolio logic is independent from pandas.
- API and Dashboard can reuse the same objects.
- Scoring changes do not leak into portfolio calculations.
