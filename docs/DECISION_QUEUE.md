# Decision Queue

`output/dados/decision_queue.json` is the versioned, read-only foundation of
the Atlas Decision Cockpit. It consolidates decisions already produced by the
official portfolio sell engine and states already produced by the Active
Watchlist. It never computes a score or creates a competing recommendation.

Groups:

- `EXECUTE`: official `SELL`/`TRIM` actions and Watchlist candidates whose
  objective promotion trigger fired. Watchlist items use the advisory action
  `REVIEW_FOR_PURCHASE`; they are not executed buys.
- `INVESTIGATE`: official `REVISAR`, expired deadlines and discard reviews.
- `WAIT`: valid promotion conditions not yet reached.
- `MONITOR`: holdings in `HOLD`, informational `ACOMPANHAR` signals and
  Watchlist entries still analyzing.

Every item preserves its engine, reason, priority and source metadata and
carries `advisory_only: true`. The contract is embedded in `dashboard.json`
(v1.2) and served by the read-only API at `GET /decision-queue`.
