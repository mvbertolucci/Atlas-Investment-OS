# ADR-006 — Rebalance is advisory only

## Status

Accepted

## Decision

The Rebalance Engine generates suggestions only. It never sends orders to a broker.

## Consequences

- Lower operational risk.
- Clear separation between analysis and execution.
- Easier testing and auditing.
