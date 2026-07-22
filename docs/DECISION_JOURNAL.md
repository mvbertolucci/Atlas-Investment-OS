# Decision Journal

`output/dados/decision_journal.json` is the append-only audit log of explicit
human reviews over a specific versioned Decision Queue item.

Each queue item has a deterministic `decision_id` derived from queue generation
time, symbol, action and engine. A journal event records `ACCEPTED`, `REJECTED`
or `DEFERRED`, requires a non-empty reason, preserves the original symbol,
action, engine and queue timestamp, and has its own deterministic event ID.
Exact duplicate events are rejected; a later event may supersede the latest
human status without deleting history.

Example:

```powershell
python -m decision.journal DECISION_ID ACCEPTED "Evidência confirmada"
```

Optional `--queue` and `--journal` paths support testing or isolated workflows.
The dashboard and cockpit expose only aggregate read-only counts. There is no
web mutation endpoint and the journal never executes a trade.

An `ACCEPTED` status is the prerequisite for manually recording a real
`SELL`/`TRIM` fill in the separate [Execution Ledger](EXECUTION_LEDGER.md).
Acceptance itself is not execution and sends no order.
