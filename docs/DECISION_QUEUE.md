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

## Decision Cockpit

The same queue is rendered without recomputation to
`output/relatorios/decision_cockpit.html` — the single human page ("Atlas —
Hoje"). It is organized by a rigid three-tier hierarchy rather than the four
raw queue groups: **Agir agora** (EXECUTE + INVESTIGATE, on top), **Oportunidades**
(buy candidates outside the portfolio, plus waiting entry triggers) and
**Acompanhar** (MONITOR, collapsed in a `<details>` so it does not compete with
sell/review). It also carries the portfolio-health summary and historical
evidence that used to live in the retired `decision_brief.html`. Each decision
is a card with reason, engine and available metadata. It contains no forms or
mutation controls; its purpose is immediate visual triage over the versioned
read-only contract.

When a portfolio scenario is available, the cockpit also summarizes released
cash, post-trade cash weight and turnover. It does not add replacement buys.

Each queue item carries `missing_evidence` (the union of
`missing_required_features` and `risk_evidence_missing`, minus the "Nenhum"
placeholder; additive to contract v1.1). A card whose `decision_confidence` or
`data_coverage` is below the confidence floor (60) renders a short explanation:
which fields are missing (e.g. BRK-B → the annual Piotroski F-Score), the
effect on the decision (the engine keeps it under review instead of acting) and
how to refresh the evidence (recollect the ticker via the `atualizar-ticker`
skill).

Queue items carry a deterministic `decision_id` (hash of symbol, action and
engine — stable across runs since contract v1.1, ADR-040) used by the
append-only Decision Journal. The cockpit shows only aggregate
accepted/rejected/deferred counts and remains read-only.

Each run also writes an immutable snapshot of the full queue contract to
`output/dados/history/decision_queue/decision_queue_<generated_at>.json`,
the raw material for run-over-run comparison ("what changed since the last
run"). Snapshots are runtime artifacts and are not versioned in Git.

## Run-over-run delta

`decision/delta.py` diffs the current queue against the most recent earlier
snapshot and writes `output/dados/decision_delta.json` (contract v1.0). The
cockpit renders it as the top "Mudou desde a última execução" section, so the
first thing a human sees is the change, not the whole portfolio repeated.

Because the `decision_id` identity is `symbol|action|engine`, an action
escalation (e.g. REVISAR → SELL on the same holding) would naively look like
one item leaving and another entering. `build_decision_delta` pairs those by
`(symbol, engine)` and reports them as an **action transition** — the single
most decision-relevant signal — instead of an exit plus an entry. It also
reports items that entered, items that exited, and same-decision changes:
group moves, score moves above a threshold (default 5.0 points; appearing or
disappearing evidence is always material regardless of threshold) and thesis
revisions. `current_weight` is deliberately excluded — it drifts with price
every run and would be permanent noise. Items with no material change are
counted, not listed, so the section stays focused. The first run has no
baseline and says so.
