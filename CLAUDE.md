# Atlas Investment OS — Claude Code Entry Point

@AGENTS.md
@docs/ATLAS_CONTEXT.md
@docs/PROJECT_CONSTITUTION.md

## Session startup

Before changing files:

1. Run `git status --short --branch` and `git log -5 --oneline`.
2. Confirm that the working tree is clean or identify pre-existing user changes.
3. Read the relevant architecture, backlog and tests for the requested task.
4. State the intended scope and preserve unrelated work.

## Windows commands

Use the repository virtual environment when it exists:

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe run_all.py
```

For the full regression gate:

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q --cov=. --cov-config=.coveragerc --cov-report=term-missing --cov-fail-under=80
```

## Repository safety

- Never use `git push --force`, destructive reset or broad file deletion.
- Do not commit `.env`, local databases, logs, reports, caches or credentials.
- Do not push, merge, tag or publish unless the user explicitly requests it.
- Do not change governed financial configuration without explaining the
  financial effect and adding focused regression tests.
- Keep one primary objective per commit and leave the working tree clean.

## Current handoff

- Released version: `v1.2.0`; development baseline: `PR-033` + real SEC
  EDGAR data acquisition, now end to end (15 fields, checkpointed
  collector, ratio derivation).
- Validation baseline: 467 tests / 87.33% production coverage.
- v1.1 Integrated Portfolio Intelligence and v1.2 Outcome Analytics are
  complete.
- v2.0 Platform is in progress. The point-in-time data contract is complete;
  the walk-forward *mechanism* (`backtesting/walk_forward.py`) is merged.
  `backtesting/sec_edgar.py` + `sec_edgar_collector.py` acquire 15 native
  fundamental fields in checkpointed, resumable batches, and
  `point_in_time_fundamentals.py` derives the *ratios*
  `config/features.yaml` actually scores on. **The full loop is proven
  against live SEC data**: replaying a real decision for Apple and
  Microsoft produced derived gross margins matching each company's real
  historical range (48.6% / 68.2%) and two genuinely different Investment
  Scores (52.9 / 58.9) instead of both collapsing to a neutral 50. Still
  not a complete historical dataset -- `f_score_annual` (needs two fiscal
  years) and `altman_z`/valuation multiples (need price, which SEC EDGAR
  lacks) are unbuilt; see `docs/SEC_EDGAR_DATA.md`. In parallel: the real
  portfolio is wired end to end (`portfolio.rebalance_mode = "sell_only"`
  by default), an on-demand sell/buy priority classification exists
  (`priority/`), two more screeners (broad US market, US-listed ADRs) are
  infrastructure-only, and `portfolio/model_portfolio.py` can run ranking
  over any of the three screeners via `--universe-policy`/`--label` — see
  `docs/ATLAS_CONTEXT.md` section 6.
- Open threads, in priority order: (1) pair a historical price series
  (unlocks valuation multiples and `altman_z`); (2) two-fiscal-year replay
  for `f_score_annual`; (3) run the broad-market/ADR collections when
  resumed; (4) PR-034 portfolio validation, once a real dataset is usable
  at scale (today's real verification covers 2 companies, one date).
