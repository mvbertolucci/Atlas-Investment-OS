# ADR-004 — Presentation consumes domain models

## Status

Accepted

## Decision

Presentation components should consume domain objects such as
`CompanyReport` instead of reading the raw scoring DataFrame directly.

## Consequences

- Lower coupling to pandas
- Easier API and Dashboard development
- Easier serialization
- Clearer tests
