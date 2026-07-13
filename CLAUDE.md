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

- Released version: `v1.2.0`; development baseline: `PR-037`.
- Validation baseline: 411 tests / 86.61% production coverage.
- v1.1 Integrated Portfolio Intelligence and v1.2 Outcome Analytics are
  complete.
- v2.0 Platform is in progress. The point-in-time data contract is complete;
  deterministic walk-forward backtesting remains the next analytical
  increment. In parallel: the real portfolio is wired end to end
  (`portfolio.rebalance_mode = "sell_only"` by default), an on-demand
  sell/buy priority classification exists (`priority/`), and two more
  screeners (broad US market, US-listed ADRs) are infrastructure-only —
  see `docs/ATLAS_CONTEXT.md` section 6.
- Next planned increment: parametrize `portfolio/model_portfolio.py` to
  accept any of the three universe/ranking policies (today hardcoded to
  the S&P 500 one), so ranking/buy-priority work over the broad-market or
  ADR screener as soon as their collection eventually runs.
