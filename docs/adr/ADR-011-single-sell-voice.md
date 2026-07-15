# ADR-011 — Portfolio rebalance is the single sell voice

**Status:** Accepted  
**Date:** 2026-07-15

## Context

Atlas exposed two actions for the same real holding. The stateful portfolio
engine evaluated thesis, confidence and the named `distress`,
`valuation_stretch`, `fundamental_decay` and `relative_decay` rules, while
`priority.build_sell_priority` independently reduced Deal Breaker presence to
`SELL` or `HOLD`. The results could disagree in the same run.

## Decision

`PortfolioReport.rebalance.actions` is the only authoritative source of sell
actions for real holdings. Priority is a read-only ordering and presentation
layer: it copies `SELL`, `TRIM`, `HOLD` or `REVISAR`, plus the official reason,
triggered rules, missing data and priority. Ranking data may enrich the item
with Investment Score and Deal Breakers, but cannot determine or override its
action.

When no `PortfolioReport` is available, sell priority is empty. It must not
infer an action from ranking data.

## Alternatives considered

- Keep the Deal Breaker-only classifier and relabel it. Rejected because two
  action-like fields would remain visible for one holding.
- Re-run sell rules inside Priority. Rejected because it would duplicate
  state, thesis and confidence inputs and could drift again.

## Consequences

- Portfolio rebalance, Priority, API, SDK and Dashboard expose one sell voice.
- Priority can represent `TRIM` and `REVISAR`, not only `SELL/HOLD`.
- The standalone CLI also needs `portfolio_report.json` for sell priority.
- Deal Breakers remain visible as diagnostic context.
- No scoring weight, threshold, Deal Breaker or sell-rule semantic changes.

## Migration and rollback

The JSON contract is additive: existing fields remain and official-action
metadata is added. Consumers must tolerate an empty sell list when no portfolio
report exists. Rollback consists of reverting this ADR and the Priority wiring;
it would restore the known conflicting classifier and is not recommended.
