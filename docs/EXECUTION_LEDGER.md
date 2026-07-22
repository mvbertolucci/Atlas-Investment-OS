# Execution Ledger

`output/dados/execution_ledger.json` is the append-only record of real fills
explicitly informed by a human. It is evidence, not an order-management or
brokerage integration: recording an event sends no order and changes no
portfolio position.

The first governed increment accepts only `SELL` and `TRIM` Decision Queue
items whose latest Decision Journal status is `ACCEPTED`. A later `REJECTED`
or `DEFERRED` event blocks execution recording. Each fill stores the linked
`decision_id`, symbol, action, quantity, price, fees, currency, execution and
recording timestamps, gross value and net cash delta.

Example:

```powershell
python -m decision.execution DECISION_ID 10 25.50 2026-07-22T15:30:00 --fees 1.00
```

Optional `--queue`, `--journal`, `--ledger` and `--currency` arguments support
isolated workflows. Quantity and price must be positive, fees non-negative and
not greater than gross value. Exact duplicate fills are rejected. Partial fills
are represented by separate events with distinct execution details or times.

The dashboard and Decision Cockpit expose aggregates only: fill count,
distinct decisions, gross sell value, fees and net cash delta. Individual
execution evidence remains in the ledger artifact.

## Operational sequence

1. Generate the Decision Queue.
2. Review and explicitly mark the decision `ACCEPTED` in the Decision Journal.
3. Execute outside Atlas, using the authorized brokerage process.
4. Record the actual fill in the Execution Ledger.
5. Reconcile the next portfolio import against ledger evidence.

Step 5 remains a separate future control; this increment does not infer fills,
update holdings or authorize purchases.
