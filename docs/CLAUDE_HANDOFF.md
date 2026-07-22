# Claude Handoff — 2026-07-22

This is the current bounded handoff for the next Claude Code session. Read it
after `AGENTS.md` and before editing. `docs/ATLAS_CONTEXT.md` remains the broad
project context; this file describes the latest implementation chain.

## Repository state

- Branch: `master`.
- Working tree at handoff: clean.
- Local branch after this handoff commit: **11 commits ahead of `origin/master`**,
  not pushed. Do not
  push, merge, tag or publish without Marcus's explicit approval.
- Declared release remains `v1.2.0`; no release bump was authorized.
- Full regression gate: **1,125 tests passing** on 2026-07-22.
- Latest implementation commit: `7af6cb0 feat(portfolio): automate custody
  reconciliation`; the following commit is the documentation-only handoff.

Start by running:

```powershell
git status --short --branch
git log -10 --oneline
.\.venv\Scripts\python.exe -m pytest -q
```

If any result differs, report the mismatch before changing files. Do not reset
or discard uncommitted work.

## Latest coherent product chain

The latest ten atomic commits turn the broad market/ADR screeners and Watchlist
into an auditable decision flow:

1. `0ed298e` — ADR candidates included in automatic Watchlist curation.
2. `11eeb65` — consolidated S&P 500 / broad market / ADR opportunity funnel.
3. `1def8f7` — Watchlist becomes an active queue with state, analytical origin,
   entry rank/score, review SLA and objective promotion/discard conditions.
4. `d02436f` — consolidated advisory Decision Queue (`EXECUTE`, `INVESTIGATE`,
   `WAIT`, `MONITOR`).
5. `ff0b861` — responsive Decision Cockpit HTML.
6. `f3111e8` — advisory pre-trade portfolio scenario for official `SELL`/`TRIM`.
7. `a83b771` — append-only human Decision Journal.
8. `bea4419` — append-only real-fill Execution Ledger.
9. `e680bb1` — diagnostic execution/custody reconciliation.
10. `7af6cb0` — automatic custody snapshot history and consecutive-window
    reconciliation.

The decision boundary is strict:

```text
screeners -> opportunity funnel -> active Watchlist -> Decision Queue
          -> human ACCEPTED/REJECTED/DEFERRED journal event
          -> explicitly informed SELL/TRIM fill
          -> custody snapshot comparison -> reconciliation status
```

No component sends brokerage orders, purchases securities, mutates portfolio
positions or promotes `REVIEW_FOR_PURCHASE` into an automatic buy.

## Current contracts and artifacts

- Dashboard contract: `1.7` (`dashboard/contract.py`).
- `output/dados/market_opportunity_funnel.json` — pre-mutation source funnel.
- `output/dados/decision_queue.json` — deterministic decision IDs and groups.
- `output/relatorios/decision_cockpit.html` — read-only responsive cockpit.
- `output/dados/portfolio_scenario.json` — advisory SELL/TRIM impact.
- `output/dados/decision_journal.json` — append-only human review evidence.
- `output/dados/execution_ledger.json` — append-only actual fill evidence.
- `output/dados/portfolio_custody_history.json` — append-only quantity snapshots.
- `output/dados/execution_reconciliation.json` — latest consecutive-window
  reconciliation.

Runtime artifacts under `output/` are ignored and must not be committed.

## Operational commands

Human review:

```powershell
.\.venv\Scripts\python.exe -m decision.journal DECISION_ID ACCEPTED "reason"
```

Record a real fill only after it occurred outside Atlas:

```powershell
.\.venv\Scripts\python.exe -m decision.execution DECISION_ID 10 25.50 2026-07-22T15:30:00 --fees 1.00
```

Manual reconciliation remains available for isolated snapshots:

```powershell
.\.venv\Scripts\python.exe -m decision.reconciliation before.json after.json `
  --baseline-at 2026-07-22T09:00:00 `
  --current-at 2026-07-23T09:00:00
```

Normal portfolio/dashboard runs now capture custody automatically. Two complete
snapshots are required; partial dashboard portfolio views are deliberately not
accepted as custody evidence.

## Real runtime state last observed

- Broad collection: 6,959 observed; 2,429 eligible; 794 candidates in the
  latest safeguarded market report.
- ADR policy: 501 eligible; 219 candidates.
- Consolidated opportunity preview: 1,033 unique safeguarded, 236 qualified,
  top 30 selected.
- Real portfolio: 18 holdings, about USD 84.2k; official actions last observed:
  3 `SELL` (AVAV, CLF, FMC), 6 `REVISAR`, 7 `ACOMPANHAR`, 2 `HOLD`.
- Decision Queue last observed: 3 execute, 6 investigate, 0 wait, 49 monitor.
- Execution Ledger was initialized empty. No fill was inferred or recorded for
  AVAV, CLF or FMC; therefore no real reconciliation result was fabricated.

These are ignored runtime observations, not committed truth. Re-read current
artifacts before making operational claims.

## Important implementation boundaries

- `decision/queue.py` copies official portfolio actions and active-Watchlist
  states; it does not recompute scores or recommendations.
- `decision/journal.py` requires explicit status plus non-empty reason and
  preserves all events. Latest status controls eligibility for execution.
- `decision/execution.py` accepts only `SELL`/`TRIM` whose latest journal state
  is `ACCEPTED`. It supports separate partial fills and rejects exact duplicates.
- `portfolio/custody_history.py` captures only complete portfolio reports with
  `generated_at` and `holdings`; identical reruns are idempotent.
- `decision/reconciliation.py` groups fills by symbol, uses only fills strictly
  after baseline and at/before current snapshot, and reports `CONFIRMED`,
  `PARTIAL`, `NOT_REFLECTED`, `VARIANCE` or `UNVERIFIABLE`.
- A missing symbol in a complete current snapshot means zero; missing from the
  baseline is never inferred and becomes `UNVERIFIABLE`.
- Governed scoring, thresholds, Deal Breakers and sell rules were not changed
  by this ten-commit chain.

## Recommended next bounded increment

Add an **exception workflow for reconciliation findings**, not automatic
correction. It should create an investigation item for `PARTIAL`,
`NOT_REFLECTED`, `VARIANCE` and `UNVERIFIABLE`, with owner/status/reason and an
append-only resolution event. Preserve the original reconciliation artifact,
never rewrite the ledger or custody history, and do not add broker connectivity.

Before implementing, inspect:

- `decision/reconciliation.py` and its tests;
- `decision/journal.py` for append-only event conventions;
- `decision/cockpit.py` and Dashboard Contract 1.7;
- `docs/EXECUTION_RECONCILIATION.md` and `docs/CUSTODY_HISTORY.md`.

Keep this as one atomic commit, update contracts deliberately, run the complete
suite and leave the working tree clean.

## Ready-to-paste first prompt

```text
Read CLAUDE.md, AGENTS.md and docs/CLAUDE_HANDOFF.md fully. Do not edit yet.
Verify git status, the last 11 commits, that master is 11 commits ahead of
origin/master, and run the full pytest suite expecting 1,125 passing tests.
Summarize the implemented screener -> active Watchlist -> Decision Queue ->
human journal -> Execution Ledger -> custody reconciliation chain and its
no-order/no-automatic-buy boundaries. Report any mismatch before proceeding.
Do not push, merge, tag or change governed financial configuration without
explicit approval.
```
