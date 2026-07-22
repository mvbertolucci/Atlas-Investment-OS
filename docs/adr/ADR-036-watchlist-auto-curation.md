# ADR-036 — Automatic watchlist inclusion/exclusion, additional to the manual gate

**Status:** Accepted
**Date:** 2026-07-21

## Context

`config/watchlist.csv` was a 100% manually-curated file: `run_all.py` never
wrote to it in any mode. This was explicitly confirmed as intentional
design with the user on 2026-07-18 ("manual gate, not a gap") — the only
writers were the CLI (`watchlist/promote.py::promote_to_watchlist`) and the
Excel workbook flow (`watchlist/candidates_workbook.py` +
`watchlist/apply_candidates_workbook.py`), both requiring the user to
review and apply every addition by hand.

On 2026-07-21 the user explicitly requested a new, **additional** flow: when
running the full sampling (`--full`), automatically include the top 30
candidates by score from the S&P500 + broad market screeners, and exclude
existing watchlist items whose score fell below a threshold — while keeping
the manual path unchanged.

This directly supersedes the 2026-07-18 decision. It does not contradict it
silently: the manual gate remains fully intact and untouched; the new path
is additive, gated by its own config, and does not remove the user's
ability to curate by hand.

## Decision

1. **New `source` column** (`manual`\|`auto`) on `config/watchlist.csv`
   (`watchlist/csv_schema.py`, `watchlist/models.py::WatchlistEntry`,
   `watchlist/loader.py`) distinguishes hand-curated rows from
   automatically-added ones. Every pre-existing row (none had this column)
   defaults to `manual` with no migration script — absence of the column is
   itself the signal. This is the only reliable mechanism found; the
   existing free-text `note` column was confirmed to be hand-typed, not
   machine-parseable.
2. **`watchlist/promote.py::remove_from_watchlist`** (new, symmetric to
   `promote_to_watchlist` — no removal primitive existed before). Both now
   share a single atomic CSV writer (`watchlist/csv_writer.py`, built on
   `storage.atomic_write.replace_with_retry`, ADR-032) — `promote_to_watchlist`
   previously wrote with a raw `open("w")`, unprotected against the same
   OneDrive-lock hazard already fixed for every other writer in this
   repository.
3. **`watchlist/auto_curation.py`** — the selection logic, config-driven via
   `config/watchlist_auto.yaml` / `watchlist/auto_policy.py::WatchlistAutoPolicy`
   (same governed-config pattern as `portfolio/sell_rules.py`):
   - **Inclusion**: combines the S&P500 (`research_ranking_report.json`),
     broad market (`research_ranking_report_market.json`) and ADR
     (`research_ranking_report_adr.json`) screener snapshots. Deduplication is
     deterministic in that order: S&P500 wins over broad market, and broad
     market wins over ADR. A candidate qualifies only
     if its **estimated** Decision (`decision/policy.py::evaluate_decision`,
     called with `risk_penalty=0.0` — the real risk penalty only exists for
     names already collected/scored in the reduced watchlist+portfolio
     universe, not the broad universe read here) is in
     `selection.qualifying_decisions` (`STRONG_BUY`/`BUY`/`ACCUMULATE`,
     confirmed with the user — matches the existing "Acumular" cutoff in
     `watchlist/screening.py`), **and** its `confidence_score` clears
     `selection.min_confidence_score` (`60.0`, the confirmed safeguard
     against the risk-penalty approximation being too optimistic). Ranked by
     Investment Score, capped at `selection.top_n` (`30`).
   - **Exclusion**: only entries with `source == "auto"`
     (`safeguards.protect_manual_entries`) and never a symbol with
     `origin == "portfolio"` in the scored frame
     (`safeguards.protect_portfolio_holdings`) — both confirmed mandatory,
     kept as explicit config rather than hardcoded so the intent stays
     visible and testable. A symbol missing from this run's scored frame,
     or with a non-numeric Investment Score, is never removed — absence of
     data is not evidence of a low score. Threshold:
     `exit.investment_score_threshold` (`40.0`).
4. **Wiring**: `IntelligenceStage.run()` (`orchestration/pipeline.py`) calls
   `intelligence_services.run_watchlist_auto_curation(...)` **before**
   `generate_watchlist_report(...)`, in the same stage. Since
   `generate_watchlist_report` re-reads `config/watchlist.csv` from disk
   (never the in-memory bootstrap frame), the auto-curation result is
   already reflected in the same run's watchlist report and Atlas Report —
   no extra plumbing needed for that. `ScoringOutput` gained a
   `research_ranking_report_path` field, computed the same way
   `broad_market_report_path`/`adr_report_path` already were (only located,
   never generated, in `mode == "full"`).
5. **Never a silent mutation** — surfaced in three independent places every
   run:
   - Console (`CompletionStage`): `Watchlist Auto : +N incluído(s), -M
     removido(s)`, plus one `[AUTO-IN]`/`[AUTO-OUT]` line per item.
   - `output/dados/watchlist_report.json::auto_curation` (new key on the
     existing `WatchlistReport` contract, not a new file).
   - A new "Curadoria Automática da Watchlist" section in the Atlas Report
     (`reports/atlas_report/render.py`), next to the existing "Sugestões
     para a watchlist" section.
6. **`config/watchlist_auto.yaml::enabled`** is the circuit breaker. Shipped
   `false` while the wiring didn't exist yet (this PR's first two commits);
   flipped to `true` only once the end-to-end wiring was built and tested
   against real disk I/O (`tests/test_application_services.py::test_intelligence_service_runs_watchlist_auto_curation_end_to_end`).

## Consequences

- `run_all.py` now writes to `config/watchlist.csv` automatically, for the
  first time. This is a deliberate, requested, and safeguarded behavior
  change — not a silent one. Turning it off requires no code change, only
  `config/watchlist_auto.yaml::enabled: false`.
- The estimated Decision used for inclusion can disagree with the
  authoritative Decision the same symbol would get once it's actually
  collected/scored inside the reduced universe on a later run (the
  `risk_penalty=0.0` approximation). This is documented, not silently
  assumed accurate — the `min_confidence_score` gate is the mitigation, not
  a fix.
- `watchlist/promote.py::promote_to_watchlist` gained a `source` parameter
  (default `"manual"`, backward compatible for every existing caller) and
  now routes through the shared atomic writer — behavior-preserving for all
  pre-existing callers (CLI, workbook).
- 34 new tests across `tests/test_watchlist_promote.py`,
  `tests/test_watchlist_remove.py`, `tests/test_watchlist_loader.py`,
  `tests/test_watchlist_auto_policy.py`, `tests/test_watchlist_auto_curation.py`,
  `tests/test_pipeline_orchestration.py`, `tests/test_application_services.py`
  — including the regression that matters most: an entry with
  `source == "auto"` that is also a real portfolio holding, with a score far
  below the exit threshold, is never auto-removed.
- No governed scoring value, weight, or threshold changes — this only adds
  new, separately-governed config (`config/watchlist_auto.yaml`).
- Since 2026-07-22, ADR candidates use the same automatic inclusion policy as
  the other broad screeners. Their provenance remains explicit in the
  candidate note (`Auto-inclusão (adr)`) and ADR-only names can enter without
  changing the qualifying decisions or confidence threshold.

## Rollback

Set `config/watchlist_auto.yaml::enabled: false` — `run_auto_curation`
short-circuits before touching the CSV, with zero code changes. Full revert:
drop the `source` column handling, `watchlist/auto_curation.py`,
`watchlist/auto_policy.py`, `config/watchlist_auto.yaml`, the
`remove_from_watchlist` addition, and the `IntelligenceStage`/
`CompletionStage`/`ReportContext` wiring described above. The manual gate
(`promote_to_watchlist`, CLI, workbook) is unaffected either way.
