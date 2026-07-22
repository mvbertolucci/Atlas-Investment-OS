# Execution Reconciliation

`output/dados/execution_reconciliation.json` compares real `SELL`/`TRIM`
fills from the Execution Ledger with two explicit, complete portfolio
snapshots. It is diagnostic and never changes holdings or ledger events.

```powershell
python -m decision.reconciliation before.json after.json `
  --baseline-at 2026-07-22T09:00:00 `
  --current-at 2026-07-23T09:00:00
```

Both JSON inputs must contain a `holdings` list with `symbol` and `quantity`.
The baseline must represent custody before the executions and the current
snapshot must represent custody after them. Execution timestamps use ISO 8601;
fills later than `--current-at` are excluded.

Statuses:

- `CONFIRMED`: observed reduction equals ledger quantity within tolerance;
- `PARTIAL`: some, but not all, of the expected reduction is visible;
- `NOT_REFLECTED`: no compatible reduction is visible;
- `VARIANCE`: the reduction exceeds or otherwise diverges from ledger fills;
- `UNVERIFIABLE`: the symbol is absent from the baseline.

An asset absent from a complete current snapshot is treated as quantity zero.
An asset absent from the baseline is never inferred as zero. Multiple fills for
the same symbol are aggregated because custody alone cannot reliably attribute
a position change among multiple decision IDs.

The Decision Cockpit and Dashboard Contract expose only status counts. The
detailed quantities, variances, execution IDs and decision IDs remain in the
reconciliation artifact for investigation.
