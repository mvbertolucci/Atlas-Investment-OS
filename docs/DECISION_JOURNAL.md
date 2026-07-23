# Decision Journal

`output/dados/decision_journal.json` is the append-only audit log of explicit
human reviews over a specific versioned Decision Queue item.

Each queue item has a deterministic `decision_id` derived from symbol, action
and engine — stable across runs (ADR-040), so a review recorded today still
refers to the same decision when tomorrow's queue is generated; the queue
generation time is stored on the event as `queue_generated_at`, an occurrence
attribute, not part of the identity. A journal event records `ACCEPTED`, `REJECTED`
or `DEFERRED`, requires a non-empty reason, preserves the original symbol,
action, engine and queue timestamp, and has its own deterministic event ID.
Exact duplicate events are rejected; a later event may supersede the latest
human status without deleting history.

Example:

```powershell
python -m decision.journal DECISION_ID ACCEPTED "Evidência confirmada"
```

Optional `--queue` and `--journal` paths support testing or isolated workflows.

Since 2026-07-22 (PR-D, ADR-041) the cockpit also records reviews interactively:
the Aceitar/Adiar/Rejeitar buttons on each card `POST /journal` to the local
API (`api.server`), which resolves the `decision_id` against the current
Decision Queue and calls the same `record_decision`. This is the **only** write
path in the otherwise read-only API. It is hardened for a personal, local tool:
the server binds `127.0.0.1` only, the write requires `Content-Type:
application/json` (a cross-site form cannot set it without a CORS preflight the
server never answers, mitigating simple CSRF), the body is size-capped, and the
write stays append-only and advisory — it never sends an order or mutates the
portfolio. The buttons only work when the page is opened from the API
(`http://127.0.0.1:8000/cockpit`, same-origin); opened as a `file://` the
buttons are disabled with an inline notice.

Each card shows a **derived status** (`decision/status.py`), computed on every
render from journal + ledger rather than stored: `novo` (no event),
`em análise` (latest DEFERRED), `decidido` (latest ACCEPTED), `descartado`
(latest REJECTED) and `executado` (a fill exists in the ledger, which dominates
because the ledger only accepts a fill over an ACCEPTED decision). This avoids a
second source of truth that could desync. The dashboard and cockpit also expose
aggregate counts.

An `ACCEPTED` status is the prerequisite for manually recording a real
`SELL`/`TRIM` fill in the separate [Execution Ledger](EXECUTION_LEDGER.md).
Acceptance itself is not execution and sends no order.
